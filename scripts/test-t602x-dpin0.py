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
static void writel(u32 v, void *p) { *(u32 *)p = v; }
'''
tests = r'''
int main(void) {
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
 puts("PASS: 27 actual DPIN0 select/disconnect cycles; source gate clears, reset restores, +0x20 untouched");
}
'''
with tempfile.TemporaryDirectory(prefix='j416s-crossbar-test-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(preamble+s+tests)
 subprocess.run(['cc','-std=gnu11','-fsanitize=address,undefined','-g',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
