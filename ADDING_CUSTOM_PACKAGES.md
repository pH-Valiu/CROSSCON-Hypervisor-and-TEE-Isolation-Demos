# Guide for buildroot - custom packages

## Steps for custom package:
- After having downloaded buildroot and extracted the tarball
- Create subfolder foo in `/buildroot/package` --> `/buildroot/package/foo` (all lowercase with dashes)
- Create *Config.in* and *foo.mk* files in foo folder
- Add `source "package/foo/Config.in"` to `/buildroot/package/Config.in` (under Miscellaneous or other, sorted alphabetically)
- Add content to Config.in (make note of the `default y` setting as well as the `depends on` or `select`)
- Add content to foo.mk (this is the hardest step probably. <br>Refer to buildroot docs for help or to https://stackoverflow.com/questions/19783795/how-to-add-my-own-software-to-a-buildroot-linux-package )
- Make sure that toolchain in global `.config` file for buildroot has the support for compiling your app

## What is happening during buildroot execution
The `foo.mk` file references the custom make file of your application you want to include.
How your application has to be compiled should therefore not be part of `foo.mk` but rather be part of the internal make file.
The default usage is specifying a download address in `foo.mk` from which the source code should be pulled containing an internal make file describing the compilation.
In the example below we supplied the code locally.

## Examples:

An exmaple for the internal code Makefile:

```
CXX := g++

.PHONY: clean all

all: helloworld 

helloworld: hello.cpp hello.h
	$(CXX) -o $@ $< 
clean:
       rm helloworld
```



An exmaple for the *foo.mk* file:
```
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
```


An exmaple for the *Config.in* file:
```
config BR2_PACKAGE_HELLOWORLD
	bool "helloworld"
	default y
	depends on BR2_INSTALl_LIBSTDCPP
	help
	  This is help text here with a limit to its
	  width

	  http://please-add-url.com

comment "helloworld needs a toolchain w/ C++"
```
