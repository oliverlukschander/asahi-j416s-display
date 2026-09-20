KDIR ?= /home/oliver/Development/omarchy/aurora-j416s/kbuild/usr/lib/modules/7.1.12-2.5-1-ARCH/build

obj-m := appledrm.o
appledrm-y := apple_drv.o afk.o dcp.o dcp_backlight.o dptxep.o iomfb.o parser.o systemep.o
appledrm-y += audio.o av.o connector.o ibootep.o iomfb_v12_3.o iomfb_v13_3.o
appledrm-y += epic/dpavservep.o plane.o
appledrm-$(CONFIG_TRACING) += trace.o

ccflags-y += -I$(src)

# Hide vmlinux so module link skips pahole/BTF (dwarves not installed).
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
