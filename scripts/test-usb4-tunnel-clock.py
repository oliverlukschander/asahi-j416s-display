#!/usr/bin/env python3
"""Compile actual tunnel-clock helpers against RAM MMIO; never open hardware."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'src/phy/atc.c').read_text()
start = source.index('struct atc_tunnel_saved_reg {')
end = source.index('static int atcphy_configure(', start)
helpers = source[start:end]
defines = '\n'.join(re.findall(r'^#define [^\n]*(?:\\\n[^\n]*)*', source, re.M))
preamble = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint8_t u8;
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((~0U << (l)) & (~0U >> (31-(h))))
#define FIELD_PREP(m,v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define lockdep_assert_held(x) ((void)0)
#define udelay(x) ((void)0)
struct apple_atcphy {
 struct { unsigned char *core; } regs;
 bool tunnel_attempted, tunnel_saved;
 u8 tunnel_rate;
 u32 tunnel_saved_regs[12];
};
static u32 ram[0x8000/4], before[0x8000/4];
static unsigned int writes, polls, fail_poll, command_count;
static u32 commands[2];
/* Independent address/mask allowlist: native tunnel sequence, not SS lanes. */
static const u32 offsets[] = {8,0x1b0,0x7000,0x2224,0x2080,0x2084,
 0x2088,0x2208,0x2220,0x2214,0x2200,0x2000};
static const u32 masks[] = {0x3ffff,0xfff,0x207c,3,0xffffffff,0xfffffff,
 0x7fffff,0x1f0000,0x80,1,0x54,0x1ffffff9};
static u32 readl(void *p) {
 uintptr_t off = (unsigned char *)p - (unsigned char *)ram;
 assert(off < sizeof(ram) && !(off & 3));
 return ram[off/4];
}
static void core_mask32(struct apple_atcphy *p, u32 reg, u32 mask, u32 value) {
 assert(p->regs.core == (unsigned char *)ram);
 unsigned int i;
 for (i=0; i<ARRAY_SIZE(offsets); i++) if (reg==offsets[i]) break;
 assert(i<ARRAY_SIZE(offsets));
 assert(!((mask|value) & ~masks[i]));
 u32 next=(ram[reg/4]&~mask)|value;
 if (reg==0x2000 && (next&1) && !(ram[reg/4]&1)) {
  assert(command_count<2);
  commands[command_count++]=(next>>3)&0x1ffffff;
 }
 ram[reg/4]=next;
 writes++;
}
#define core_set32(p,r,v) core_mask32(p,r,0,v)
#define core_clear32(p,r,v) core_mask32(p,r,v,0)
/* The four poll points are ready, command 0 ACK, PLL lock, command 0x2000 ACK. */
#define readl_poll_timeout(addr,value,condition,delay,timeout) ({ \
 (void)(delay); assert((timeout)==10000); \
 polls++; (value)=readl(addr); \
 int result=(polls==fail_poll) ? -ETIMEDOUT : ((condition) ? 0 : -ETIMEDOUT); \
 result; })
static struct apple_atcphy fresh(void) {
 for (unsigned int i=0; i<ARRAY_SIZE(ram); i++) ram[i]=0xa5a50000U ^ i;
 ram[0x7000/4] &= ~((1U<<15)|(1U<<13)|(1U<<14));
 ram[0x2200/4] &= ~0x54U;
 ram[0x2000/4] &= ~1U;
 ram[0x2000/4] |= 2; /* read-only ACK */
 ram[0xa74/4] |= 1;
 ram[0x7044/4] |= 8;
 memcpy(before,ram,sizeof(ram));
 writes=polls=fail_poll=command_count=0;
 return (struct apple_atcphy){.regs.core=(unsigned char *)ram};
}
'''
tests = r'''
int main(void) {
 const u8 rates[]={6,10,20,30};
 const u32 selectors[]={4,3,1,0};
 for (unsigned int i=0;i<4;i++) {
  struct apple_atcphy p=fresh();
  assert(atc_tunnel_start(&p,rates[i])==0);
  assert(p.tunnel_saved && p.tunnel_attempted && p.tunnel_rate==rates[i]);
  assert(command_count==2 && commands[0]==0 && commands[1]==0x2000);
  assert(ram[0x2080/4]==0x1e0e021c);
  assert((ram[0x2084/4]&0xfffffff)==0);
  assert((ram[0x2088/4]&0x7fffff)==0x654a00);
  assert((ram[0x7000/4]&0x207c)==(0x200c|(selectors[i]<<4)));
  unsigned int w=writes;
  assert(atc_tunnel_start(&p,rates[i])==0 && writes==w);
  assert(atc_tunnel_start(&p,rates[(i+1)%4])==-EBUSY && writes==w);
  /* Concurrent unrelated bit changes must survive the masked restore. */
  ram[8/4]^=BIT(31); before[8/4]^=BIT(31);
  atc_tunnel_restore(&p);
  assert(!memcmp(ram,before,sizeof(ram)));
  w=writes;
  atc_tunnel_restore(&p);
  assert(writes==w && !p.tunnel_saved && !p.tunnel_rate);
  assert(atc_tunnel_start(&p,rates[i])==-EALREADY && writes==w);
 }
 for (unsigned int fail=1;fail<=4;fail++) {
  struct apple_atcphy p=fresh(); fail_poll=fail;
  assert(atc_tunnel_start(&p,10)==-ETIMEDOUT);
  assert(!p.tunnel_saved && !p.tunnel_rate);
  assert(!memcmp(ram,before,sizeof(ram)));
  assert(fail!=1 || writes==0);
  if(fail!=1) assert(atc_tunnel_start(&p,10)==-EALREADY);
 }
 const u32 busyregs[]={0x7000,0x7000,0x7000,0x2200,0x2200,0x2200,0x2000};
 const u32 busybits[]={BIT(15),BIT(13),BIT(14),4,16,64,1};
 for(unsigned int i=0;i<ARRAY_SIZE(busyregs);i++) {
  struct apple_atcphy p=fresh(); ram[busyregs[i]/4]|=busybits[i];
  assert(atc_tunnel_start(&p,10)==-EBUSY && !writes);
 }
 struct apple_atcphy p=fresh();
 assert(atc_tunnel_start(&p,0)==-EINVAL && !writes);
 assert(atc_tunnel_start(&p,9)==-EINVAL && !writes);
 puts("PASS: 4 native rate descriptors; idempotence; all 4 poll failures; rollback; 7 busy guards; invalid rates; MMIO allowlist");
}
'''
with tempfile.TemporaryDirectory(prefix='j416s-tunnel-test-') as tmp:
    path = Path(tmp)
    (path/'test.c').write_text(preamble+'\n'+defines+'\n'+helpers+'\n'+tests)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                    '-o',str(path/'test'),str(path/'test.c')],check=True)
    subprocess.run([str(path/'test')],check=True)
