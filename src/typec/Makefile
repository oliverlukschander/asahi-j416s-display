KDIR ?= /home/oliver/Development/omarchy/aurora-j416s/kbuild/usr/lib/modules/7.1.12-2.5-1-ARCH/build

obj-m := tps6598x-core.o tps6598x.o sn201202x.o
tps6598x-core-y := core.o
tps6598x-core-y += trace.o
tps6598x-y := i2c.o
sn201202x-y := spmi.o

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
