####################################################################
#
# nexmon
#
####################################################################

NEXMON_VERSION = 1.0
NEXMON_KERNEL_VERSION = 5.10.92-v8+
NEXMON_SOURCE = $(NEXMON_KERNEL_VERSION).tar.xz
NEXMON_SITE = https://raw.githubusercontent.com/pH-Valiu/nexmon_csi_bin/main/base
NEXMON_LICENSE = MIT-1
NEXMON_INSTALL_STAGING = NO
NEXMON_DEPENDENCIES = qpdf gmp

KERNEL_VERSION = 5.10.92-v8+

define NEXMON_EXTRACT_CMDS
	cp $(NEXMON_DL_DIR)/$(NEXMON_KERNEL_VERSION).tar.xz $(@D)/.
	tar -xvf $(@D)/$(NEXMON_KERNEL_VERSION).tar.xz -C $(@D)/.
endef

define NEXMON_INSTALL_TARGET_CMDS
        $(INSTALL) -D -m 0755 $(@D)/$(NEXMON_KERNEL_VERSION)/nexutil/nexutil $(TARGET_DIR)/usr/bin/nexutil
        $(INSTALL) -D -m 0755 $(@D)/$(NEXMON_KERNEL_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/bin/mcp
        $(INSTALL) -D -m 0755 $(@D)/$(NEXMON_KERNEL_VERSION)/makecsiparams/makecsiparams $(TARGET_DIR)/usr/bin/makecsiparams
        $(INSTALL) -D -m 0755 $(@D)/$(NEXMON_KERNEL_VERSION)/patched/brcmfmac43455-sdio.bin $(TARGET_DIR)/lib/firmware/brcm/brcmfmac43455-sdio.bin
	$(INSTALL) -D -m 0755 $(@D)/$(NEXMON_KERNEL_VERSION)/patched/brcmfmac.ko $(TARGET_DIR)/lib/modules/$(KERNEL_VERSION)/kernel/drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko
endef


$(eval $(generic-package))
