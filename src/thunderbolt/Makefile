KDIR ?= /home/oliver/Development/omarchy/aurora-j416s/kbuild/usr/lib/modules/7.1.12-2.5-1-ARCH/build

obj-m := thunderbolt.o
thunderbolt-objs := nhi.o ctl.o tb.o switch.o cap.o pci.o path.o tunnel.o eeprom.o
thunderbolt-objs += domain.o dma_port.o icm.o property.o xdomain.o lc.o tmu.o usb4.o
thunderbolt-objs += usb4_port.o nvm.o retimer.o quirks.o clx.o debugfs.o

ccflags-y += -I$(src)

all:
	@if [ -f $(KDIR)/vmlinux ] && [ ! -f $(KDIR)/vmlinux.btf-hide ]; then \
		mv $(KDIR)/vmlinux $(KDIR)/vmlinux.btf-hide; \
	fi
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules; \
	rc=$$?; \
	if [ -f $(KDIR)/vmlinux.btf-hide ]; then mv $(KDIR)/vmlinux.btf-hide $(KDIR)/vmlinux; fi; \
	exit $$rc

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
