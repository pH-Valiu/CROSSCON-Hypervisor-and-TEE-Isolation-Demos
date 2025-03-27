############################################################################
#
# helloworld
#
############################################################################

HELLOWORLD_VERSION = 1.0
HELLOWORLD_SITE = $(HELLOWORLD_PKGDIR)/src
HELLOWORLD_SITE_METHOD = local
HELLOWORLD_LICENSE = GPL-3.0+
HELLOWORLD_INSTALL_STAGING = NO

define HELLOWORLD_BUILD_CMDS
	$(MAKE) CXX="$(TARGET_CXX)" -C $(@D) all
endef

define HELLOWORLD_INSTALL_TARGET_CMDS
	$(INSTALL) -D -m 0755 $(@D)/helloworld $(TARGET_DIR)/usr/bin
endef

define HELLOWORLD_PERMISSIONS
	/usr/bin/helloworld f 4755 root root - - - - -
endef

$(eval $(generic-package))
