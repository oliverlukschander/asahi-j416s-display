#!/usr/bin/env python3
"""Exercise the actual crossbar set() with RAM-backed register access only."""
from pathlib import Path
import subprocess
import tempfile
import sys
source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'src/mux/apple-display-crossbar.c'
s = source.read_text()
s = s[s.index('#define T602X_FIFO_WR_DPTX_CLK_EN'):s.index('static int apple_dpxbar_set(struct')]
preamble = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define assert(c) do { if (!(c)) { fprintf(stderr, "FAIL: %s\n", #c); exit(1); } } while (0)
#include <errno.h>
typedef uint32_t u32;
typedef int spinlock_t;
#define __iomem
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((~0U << (l)) & (~0U >> (31-(h))))
#define FIELD_PREP(mask,val) (((val) << __builtin_ctz(mask)) & (mask))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define scnprintf snprintf
#define dev_info(...) ((void)0)
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define spin_lock_irqsave(lock, flags) ((void)(lock), (flags)=0)
#define spin_unlock_irqrestore(lock, flags) ((void)(lock), (void)(flags))
#define udelay(n) ((void)(n))
#define MUX_IDLE_DISCONNECT (-2)
struct device;
struct mux_control_ops;
struct mux_control { void *chip; unsigned int index; };
#define mux_chip_priv(chip) (chip)
#define mux_control_get_index(mux) ((mux)->index)
static u32 readl(void *p) { return *(u32 *)p; }
static u32 *watched;
static unsigned writes;
static u32 *record_base;
static unsigned recorded[128], nrecorded;
static void writel(u32 v, void *p) {
 if(record_base) { assert(nrecorded<128); recorded[nrecorded++]=((u32 *)p-record_base)*4; }
 if (watched) {
  unsigned off=(u32 *)p-watched;
  const unsigned allowed[]={0x004,0x014,0x024,0x008,0x018,0x028,
                            0x000,0x00c,0x01c,0x034,0x02c};
  bool ok=false;
  for(unsigned i=0;i<sizeof(allowed)/sizeof(allowed[0]);i++)
   if(off*4==allowed[i]) ok=true;
  assert(ok); /* no selector rewrite, old +050/+070 writes or other port */
  if(off*4==0x000 || off*4==0x00c) assert(v & 4);
  if(off*4==0x004 || off*4==0x014) assert(!(v & 4));
  if(off*4==0x024) assert(!(v & 1));
  writes++;
 }
 *(u32 *)p = v;
}
'''
tests = r'''
int main(void) {
 {
  u32 regs[0x1000/4]={0};
  struct apple_dpxbar x={.regs=regs,.selected_dispext={-1,-1,-1},.defer_dpin0_bringup=true};
  struct mux_control m={.chip=&x,.index=MUX_DPIN0};
  regs[4/4]=0x1ff; regs[0x14/4]=0x1ff; regs[0x24/4]=0x111;
  record_base=regs;nrecorded=0;
  assert(apple_dpxbar_set_t602x(&m,3)==-EINVAL && nrecorded==0);
  x.selected_dispext[MUX_DPPHY]=2;
  assert(apple_dpxbar_set_t602x(&m,2)==-EBUSY && nrecorded==0);
  x.selected_dispext[MUX_DPPHY]=-1;
  assert(apple_dpxbar_set_t602x(&m,2)==0);
  assert(nrecorded==1 && recorded[0]==0x30 && regs[0x30/4]==0x2002);
  assert(regs[0]==0 && regs[0x34/4]==0 && regs[4/4]==0x1ff);
  /* ACTIVATE's deselect/select must still leave all gates off. */
  assert(apple_dpxbar_set_t602x(&m,MUX_IDLE_DISCONNECT)==0);
  nrecorded=0;
  assert(apple_dpxbar_set_t602x(&m,2)==0);
  assert(nrecorded==1 && recorded[0]==0x30 && regs[0]==0 && regs[0x34/4]==0);
  nrecorded=0;
  assert(t602x_right_dpin0_bring_up(&x)==0);
  assert(nrecorded==11 && regs[0]==4 && regs[0x34/4]==1);
  assert(regs[0x30/4]==0x2002);
  nrecorded=0;
  assert(apple_dpxbar_set_t602x(&m,MUX_IDLE_DISCONNECT)==0);
  for(unsigned i=0;i<nrecorded;i++) assert(recorded[i]!=0x50 && recorded[i]!=0x70);
  assert(regs[0]==0 && regs[0x34/4]==0 && regs[0x30/4]==0 && (regs[0x24/4]&1));
  record_base=NULL;
  puts("PASS: staged route selects only030; ACTIVATE leaves gates off; bring-up enables; teardown skips legacy050/070; invalid/conflicting routes refused");
 }

 for (unsigned state = 0; state < 9; state++) {
  u32 regs[0x1000/4] = {0};
  struct apple_dpxbar x = { .regs=regs, .selected_dispext={-1,-1,-1} };
  struct mux_control m = { .chip=&x, .index=MUX_DPIN0 };
  regs[0x24/4]=0x111;
  /* An unrelated clock/source must survive the DPIN0 cycle. */
  regs[0xc/4]=BIT(12);
  for (unsigned cycle=0; cycle<3; cycle++) {
   assert(apple_dpxbar_set_t602x(&m,state)==0);
   assert(regs[0xc/4] & BIT(state));
   assert(!(regs[0x24/4] & 1));
   assert(apple_dpxbar_set_t602x(&m,MUX_IDLE_DISCONNECT)==0);
   assert(!(regs[0xc/4] & BIT(state)));
   assert(regs[0xc/4] & BIT(12));
   assert(regs[0x24/4] & 1);
   assert(regs[0x20/4]==0);
   assert(x.selected_dispext[MUX_DPIN0]==-1);
  }
 }
 for(unsigned fail=0;fail<4;fail++) {
  u32 regs[0x1000/4], before[0x1000/4];
  for(unsigned i=0;i<0x1000/4;i++) regs[i]=0xa5a50000U ^ i;
  regs[0/4]|=4; regs[0xc/4]|=4;
  regs[0x804/4]&=~4U; regs[0x810/4]&=~4U; regs[0x81c/4]&=~1U;
  if(fail==1) regs[0x804/4]|=4;
  if(fail==2) regs[0x810/4]|=4;
  if(fail==3) regs[0x81c/4]|=1;
  for(unsigned i=0;i<0x1000/4;i++) before[i]=regs[i];
  struct apple_dpxbar x={.regs=regs,.selected_dispext={-1,2,-1}};
  watched=regs;writes=0;
  assert(t602x_right_dpin0_bring_up(&x)==(fail ? -ETIMEDOUT : 0));
  assert(writes==(fail ? 3U : 11U));
  const unsigned offsets[]={4,0x14,0x24,8,0x18,0x28,0,0xc,0x1c,0x34,0x2c};
  const u32 masks[]={4,4,1,4,0x30,3,4,4,1,1,4};
  for(unsigned i=0;i<0x1000/4;i++) {
   u32 mask=0;
   for(unsigned j=0;j<(fail ? 3U : 11U);j++) if(i*4==offsets[j]) mask=masks[j];
   assert(((regs[i]^before[i])&~mask)==0);
  }
  assert(x.selected_dispext[MUX_DPIN0]==2);
  if(!fail) {
   assert((regs[0x18/4]&0x30)==0x10);
   assert((regs[0x28/4]&3)==1);
   assert(regs[0x1c/4]&1);
  }
  watched=NULL;
 }
 puts("PASS: native bring-up keeps source clock active; no mux rewrite/reset assertion; all3 reset failures; unrelated fields preserved");
 puts("PASS: 27 actual DPIN0 select/disconnect cycles; source gate clears, reset restores, +0x20 untouched");
}
'''
with tempfile.TemporaryDirectory(prefix='j416s-crossbar-test-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(preamble+s+tests)
 subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined','-g',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
