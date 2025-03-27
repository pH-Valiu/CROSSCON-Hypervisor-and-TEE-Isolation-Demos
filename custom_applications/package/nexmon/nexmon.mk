####################################################################
#
# nexmon
#
####################################################################

NEXMON_VERSION = 5.10.92-v7+
NEXMON_SOURCE = $(NEXMON_VERSION).tar.xz
NEXMON_SITE = https://github.com/nexmonster/nexmon_csi_bin/tree/main/base
NEXMON_LICENSE = MIT-1
NEXMON_INSTALL_STAGING = NO

KERNEL_VERSION = 5.10.92

#define NEXMON_BUILD_CMDS
#	$(MAKE) -C $(@D) all
#endef

#define NEXMON_CSI_BIN_EXTRACT_CMDS
#    tar -xvJf $(@D)/$(KERNEL_VERSION).tar.xz -C $(@D)
#endef

define NEXMON_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/nexutil/nexutil $(TARGET_DIR)/usr/local/bin/nexutil
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/local/bin/mcp
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/local/bin/makecsiparams
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/patched/brcmfmac43455-sdio.bin $(TARGET_DIR)/lib/firmware/brcm/brcmfmac43455-sdio.bin
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_VERSION)/patched/brcmfmac.ko $(TARGET_DIR)/lib/modules/$(KERNEL_VERSION)/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko
endef


$(eval $(generic-package))
