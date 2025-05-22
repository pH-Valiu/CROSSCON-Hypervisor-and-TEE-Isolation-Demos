############################################################################
#
# automatic nexmon client
#
############################################################################

AUTOMATIC_NEXMON_CLIENT_VERSION = 1.0
AUTOMATIC_NEXMON_CLIENT_SITE = $(AUTOMATIC_NEXMON_CLIENT_PKGDIR)/files
AUTOMATIC_NEXMON_CLIENT_SITE_METHOD = local
AUTOMATIC_NEXMON_CLIENT_LICENSE = GPL-3.0+
AUTOMATIC_NEXMON_CLIENT_INSTALL_STAGING = NO

define AUTOMATIC_NEXMON_CLIENT_INSTALL_TARGET_CMDS
        $(INSTALL) -D -m 0755 $(@D)/S90nexmon $(TARGET_DIR)/etc/init.d/S90nexmon
	$(INSTALL) -D -m 0755 $(@D)/nexmon_client.py $(TARGET_DIR)/usr/bin/nexmon_client.py
endef

define AUTOMATIC_NEXMON_CLIENT_PERMISSIONS
        /etc/init.d/S90nexmon f 0755 root root - - - - -
	/usr/bin/nexmon_client.py f 0755 root root - - - - -
endef

$(eval $(generic-package))
