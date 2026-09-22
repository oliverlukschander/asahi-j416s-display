#!/usr/bin/env python3
"""Test the actual DID_CHANGE callback with a counted mock hardware boundary."""
from pathlib import Path
import subprocess
import tempfile
s=(Path(__file__).resolve().parents[1]/'src/appledrm/dptxep.c').read_text()
a=s.index('static int\ndptxport_call_did_change_link_config(')
b=s.index('static int dptxport_call_set_link_rate(',a)
code=r'''
#include <stdbool.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
struct apple_dcp { bool usb4; };
struct dptx_port { bool usb4_link_up_attempted; unsigned usb4_link_up_rate,link_rate; void *usb4_clock_phy; };
struct ep { struct apple_dcp *dcp; };
struct apple_epic_service { struct ep *ep; struct dptx_port *cookie; };
static bool usb4_native_dpin=true,usb4_tunnel_clock=true;
static unsigned calls;
static int result;
#define dcp_is_usb4_output(d) ((d)->usb4)
#define dev_info(...) ((void)0)
#define mdelay(x) ((void)0)
static int dptxport_native_dpin(struct apple_epic_service *s,bool active,bool up) {
 (void)s;assert(active);(void)up;calls++;return result;
}
'''+s[a:b]+r'''
int main(void) {
 struct apple_dcp d={.usb4=true};struct ep e={.dcp=&d};
 struct dptx_port p={.link_rate=10,.usb4_clock_phy=&d};
 struct apple_epic_service svc={.ep=&e,.cookie=&p};
 assert(dptxport_call_did_change_link_config(&svc)==0 && calls==1);
 for(int i=0;i<10;i++) assert(dptxport_call_did_change_link_config(&svc)==0 && calls==1);
 p.link_rate=20;assert(dptxport_call_did_change_link_config(&svc)==-EALREADY && calls==1);
 p.link_rate=10;p.usb4_clock_phy=NULL;
 assert(dptxport_call_did_change_link_config(&svc)==-EALREADY && calls==1);
 p.usb4_clock_phy=&d;p.usb4_link_up_rate=0;
 assert(dptxport_call_did_change_link_config(&svc)==-EALREADY && calls==1);
 p.link_rate=0;assert(dptxport_call_did_change_link_config(&svc)==0 && calls==1);
 p=(struct dptx_port){.link_rate=10,.usb4_clock_phy=&d};result=-ETIMEDOUT;
 assert(dptxport_call_did_change_link_config(&svc)==-ETIMEDOUT && calls==2);
 result=0;assert(dptxport_call_did_change_link_config(&svc)==-EALREADY && calls==2);
 p=(struct dptx_port){.link_rate=10,.usb4_clock_phy=&d};usb4_tunnel_clock=false;
 assert(dptxport_call_did_change_link_config(&svc)==0 && calls==3);
 assert(dptxport_call_did_change_link_config(&svc)==-EALREADY && calls==3);
 d.usb4=false;assert(dptxport_call_did_change_link_config(&svc)==0 && calls==3);
 puts("PASS: identical completion cached with no hardware retry; failed/changed/invalidated configurations refused; legacy/direct behavior retained");
}
'''
with tempfile.TemporaryDirectory(prefix='j416s-link-test-') as tmp:
 p=Path(tmp);(p/'test.c').write_text(code)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
