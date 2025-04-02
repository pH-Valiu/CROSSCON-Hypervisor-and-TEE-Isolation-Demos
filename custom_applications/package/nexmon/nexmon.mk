####################################################################
#
# nexmon
#
####################################################################

NEXMON_VERSION = 1.0
NEXMON_SITE = $(call github,pH-Valiu,nexmon,v$(NEXMON_VERSION))
NEXMON_DEPENDENCIES = lib
NEXMON_LICENSE = GPL-3.0
NEXMON_INSTALL_STAGING = NO
NEXMON_DEPENDENCIES = qpdf gmp

define NEXMON_BUILD_CMDS
	export KERNEL_VERSION = 5.10.92; \
	export ARCH = arm; \
	export SUBARCH = arm; \
	export KERNEL = kernel7; \
	export HOSTUNAME = Linux; \
	export PLATFORMUNAME = aarch6; \
	export NEXMON_ROOT = $(@D); \
	export CC = $(NEXMON_ROOT)/buildtools/gcc-arm-none-eabi-5_4-2016q2-linux-armv7l/bin/arm-none-eabi-; \
	export CCPLUGIN = $(NEXMON_ROOT)/buildtools/gcc-nexmon-plugin/nexmon.so; \
	export ZLIBFLATE = "zlib-flate -compress"; \
	export NEXMON_SETUP_ENV = 1; \
	export Q=@; \
	$(MAKE) install-firmware -C $(@D)/patches/bcm43455c0/7_45_189/nexmon_csi; \
	$(MAKE) -C $(@D)/utilities/nexutil; \
	$(MAKE) install -C $(@D)/utilities/nexutil;
endef


define NEXMON_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/nexutil/nexutil $(TARGET_DIR)/usr/local/bin/nexutil
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/local/bin/mcp
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/local/bin/makecsiparams
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/patched/brcmfmac43455-sdio.bin $(TARGET_DIR)/lib/firmware/brcm/brcmfmac43455-sdio.bin
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/patched/brcmfmac.ko $(TARGET_DIR)/lib/modules/$(KERNEL_VERSION)/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko
endef


$(eval $(generic-package))
