# primetcc -- TCC (TinyCC) ported to the HP Prime G1 calculator
#
# Targets:
#   make all      -> tcc.elf (TCC compiled for ARMv5TEJ, runs on the calc)
#                    rt_svc.o rt_aeabi.o (runtime for TCC-compiled programs)
#   make host     -> native (aarch64) TCC for host-side experiments
#   make test     -> run host-side tests (requires tests/emu_arm.py)
#   make clean
#
# Toolchain: arm-none-eabi-gcc (Ubuntu package gcc-arm-none-eabi)
# Target:    ARM926EJ-S (ARMv5TEJ), soft-float, freestanding, -fPIC -pie

TOPDIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TCCSRC  := $(TOPDIR)/src/tinycc-mob
HOSTTCC := $(TOPDIR)/host-tcc/bin/tcc

ARMCC  := arm-none-eabi-gcc
ARMAS  := arm-none-eabi-as
ARMAR  := arm-none-eabi-ar
ARMLD  := arm-none-eabi-ld

ARCH    := -mcpu=arm926ej-s -marm -mfloat-abi=soft
# newlib headers provide the standard <stdio.h> etc. DECLARATIONS for the
# TCC sources; we link against our own hp_libc implementations instead of
# newlib.  CONFIG_TCC_STATIC skips <dlfcn.h> (no dynamic loading on the calc).
# NOTE: keep -O0!  -O1/-O2 builds of tcc.o misbehave on the emulator (TCC
# reports "struct/union/enum already defined" during predefines); -O0 is
# reliable.  Diagnose (gcc bug vs emulator gap) before raising this.
SYSINC  := -isystem /usr/lib/arm-none-eabi/include
CFLAGS  := $(ARCH) -ffreestanding -fPIC -O0 -g -Wall \
           -I$(TOPDIR)/hp/include -I$(TOPDIR)/hp -I$(TOPDIR)/rt -I$(TCCSRC) \
           -DTCC_TARGET_ARM -DCONFIG_TCC_STATIC -DTCC_ARM_EABI -DTCC_ARM_SOFT_FLOAT -DHP_PRIME $(SYSINC)
ASFLAGS := -mcpu=arm926ej-s

# TCC's own build model: tcc.c is ONE_SOURCE and #includes libtcc.c which
# #includes tccpp.c/tccgen.c/tccelf.c/tccasm.c/tccdbg.c/tccrun.c and the
# selected backend (arm-*.c).  So a single object contains the compiler.
TCC_SRCS := tcc.c
TCC_OBJS := $(patsubst %.c,obj/%.o,$(TCC_SRCS))

HP_OBJS := obj/hp_svc.o obj/hp_libc.o obj/hp_vsnprintf.o obj/hp_input_svc.o

# PROBE=<file.c> links an extra probe object into tcc.elf (debug rounds).
# Use with HP_SVC=hp/hp_svc_test5.s (probe crt0 that bl hp_probe5).
PROBE ?=
ifneq ($(PROBE),)
PROBE_OBJS := obj/probe.o
obj/probe.o: $(PROBE) hp/hp_libc.h | obj
	$(ARMCC) $(CFLAGS) -c $(PROBE) -o $@
else
PROBE_OBJS :=
endif

all: tcc.elf rt_core.o rt_math.o rt_svc.o rt_aeabi.o

# ---------- TCC binary for the calculator ----------
tcc.elf: $(TCC_OBJS) $(HP_OBJS) $(PROBE_OBJS)
	$(ARMCC) -nostdlib -fPIC -pie -Wl,-e,_start \
	    $(TCC_OBJS) $(HP_OBJS) $(PROBE_OBJS) -lgcc -o $@
	@echo "==> $@ built.  Checking shape:"
	@readelf -h $@ | grep -E 'Type|Entry'
	@readelf -l $@ | grep -E 'LOAD|DYNAMIC'
	@readelf -r $@ | awk '{print $$3}' | sort | uniq -c | sort -rn | head -5

obj/%.o: $(TCCSRC)/%.c $(TCCSRC)/config.h | obj
	$(ARMCC) $(CFLAGS) -include $(TCCSRC)/config.h -MMD -MP -c $< -o $@

# TCC builds as ONE source: tcc.c #includes tccpp/tccgen/tccelf/... so the
# auto-deps (obj/tcc.d) must be included to rebuild on backend changes
-include obj/tcc.d

# HP_SVC selects the crt0: hp/hp_svc.s (normal) or hp/hp_svc_test.s
# (minimal startup test for on-calculator debugging).
HP_SVC ?= hp/hp_svc.s

obj/hp_svc.o: $(HP_SVC) | obj
	$(ARMAS) $(ASFLAGS) $(HP_SVC) -o $@

obj/hp_libc.o: hp/hp_libc.c hp/hp_libc.h | obj
	$(ARMCC) $(CFLAGS) -c hp/hp_libc.c -o $@

obj/hp_vsnprintf.o: hp/hp_vsnprintf.c hp/hp_libc.h | obj
	$(ARMCC) $(CFLAGS) -c hp/hp_vsnprintf.c -o $@

# RESIDENT input-hook service: compiled INTO tcc.elf so the firmware
# get_event slot always points at never-freed code (see rt/hp_input_svc.c)
obj/hp_input_svc.o: rt/hp_input_svc.c rt/hp_input_svc.h hp/hp_libc.h | obj
	$(ARMCC) $(CFLAGS) -c rt/hp_input_svc.c -o $@

# TCC's configure generates config.h for the ARM target (one-time).
$(TCCSRC)/config.h: $(TCCSRC)/configure
	cd $(TCCSRC) && ./configure --cc=arm-none-eabi-gcc --cpu=arm \
	    --cross-prefix=arm-none-eabi- --prefix=$(TOPDIR)/arm-tcc-prefix

# ---------- runtime for TCC-compiled user programs ----------
# rt_core.o: the fixed user-program runtime (hp_rt + hp_gfx + hp_input +
# hp_math + hp_string) prebuilt with GCC.  TCC on the calculator then only
# compiles the user's code.c (was ~39 KB of runtime sources per compile)
# and links the rest -- on-calc compile time drops by roughly 4x.
RT_CORE_SRCS := rt/hp_rt.c rt/hp_gfx.c rt/hp_input.c rt/hp_math.c rt/hp_string.c \
	rt/hp_fonts.c rt/hp_fonts_data.c rt/hp_sys.c \
	rt/hp_fixmath.c rt/hp_random.c rt/hp_codec.c rt/hp_gui.c rt/hp_icall.c
RT_CORE_HDRS := rt/hp_gfx.h rt/hp_input.h rt/hp_math.h rt/hp_string.h \
	rt/hp_fixmath.h rt/hp_random.h rt/hp_codec.h rt/hp_gui.h rt/hp_icall.h
RT_CORE_FLAGS := -O2 -ffreestanding -fPIC -mcpu=arm926ej-s -marm -mfloat-abi=soft \
	-I$(TOPDIR)/rt -Wall -fno-optimize-sibling-calls
rt_core.o: $(RT_CORE_SRCS) $(RT_CORE_HDRS) | rt_svc.o
	@rm -rf obj/corex && mkdir -p obj/corex
	@set -e; for f in $(RT_CORE_SRCS); do \
	    $(ARMCC) $(RT_CORE_FLAGS) -c $$f -o obj/corex/$$(basename $$f .c).o; \
	done
	@$(ARMLD) -r obj/corex/*.o -o $@
	@echo "==> rt_core.o built ($(shell wc -c < $@) bytes)"

# rt_math.o: openlibm (BSD) prebuilt with -O2; the transcendental + simple
# functions are renamed to hp_* via -D so they plug into hp_math.h.
OLM := $(TOPDIR)/rt/openlibm
OLM_FLAGS := -O2 -ffreestanding -fPIC -mcpu=arm926ej-s -marm -mfloat-abi=soft -I$(OLM)
OLM_RENAMES := -Dsin=hp_sin -Dcos=hp_cos -Dtan=hp_tan -Datan=hp_atan \
	-Datan2=hp_atan2 -Dasin=hp_asin -Dacos=hp_acos -Dexp=hp_exp \
	-Dlog=hp_log -Dlog10=hp_log10 -Dpow=hp_pow -Dsqrt=hp_sqrt \
	-Dsinh=hp_sinh -Dcosh=hp_cosh -Dtanh=hp_tanh -Dfloor=hp_floor \
	-Dceil=hp_ceil -Dfabs=hp_fabs -Dtrunc=hp_trunc -Dround=hp_round \
	-Dfmod=hp_fmod -Dfrexp=hp_frexp -Dmodf=hp_modf \
	-Dscalbn=hp_scalbn -Dexpm1=hp_expm1
OLM_SRCS := k_sin.c k_cos.c k_tan.c s_sin.c s_cos.c s_tan.c s_atan.c \
	e_atan2.c e_asin.c e_acos.c e_rem_pio2.c k_rem_pio2.c e_exp.c \
	e_log.c e_log10.c e_pow.c e_sqrt.c e_sinh.c e_cosh.c s_tanh.c \
	s_floor.c s_ceil.c s_fabs.c s_trunc.c s_round.c e_fmod.c s_frexp.c \
	s_modf.c k_exp.c s_scalbn.c s_expm1.c
rt_math.o: $(addprefix $(OLM)/,$(OLM_SRCS)) $(OLM)/cdefs-compat.h
	@rm -rf obj/olmx && mkdir -p obj/olmx
	@cd $(OLM) && $(ARMCC) $(OLM_FLAGS) $(OLM_RENAMES) -c $(OLM_SRCS)
	@mv $(OLM)/*.o obj/olmx/
	@$(ARMLD) -r obj/olmx/*.o -o $(TOPDIR)/rt_math.o
	@echo "==> rt_math.o built"
	@$(ARMCC) -c rt/rt_softfloat.c -o obj/olmx/rt_softfloat.o 2>/dev/null || true

rt_svc.o: rt/rt_svc.s
	$(ARMAS) $(ASFLAGS) rt/rt_svc.s -o $@

# __aeabi_* helpers extracted from libgcc (division, 64-bit ops)
rt_aeabi.o: | rt_svc.o
	@rm -rf obj/libgccx && mkdir -p obj/libgccx
	@$(ARMCC) $(CFLAGS) -c rt/rt_softfloat.c -o obj/libgccx/rt_softfloat.o
	@cd obj/libgccx && $(ARMAR) x $$($(ARMCC) -print-libgcc-file-name) \
	    _divsi3.o _udivsi3.o _modsi3.o _umodsi3.o _dvmd_tls.o \
	    _clzsi2.o _clzdi2.o _ctzsi2.o _ctzdi2.o \
	    _aeabi_ldivmod.o _aeabi_uldivmod.o \
	    _divdi3.o _udivdi3.o _moddi3.o _umoddi3.o _muldi3.o \
	    _udivmoddi4.o _divmoddi4.o \
	    _arm_floatdidf.o \
	    _arm_floatdisf.o _arm_floatundidf.o _arm_floatundisf.o \
	    _arm_muldf3.o _arm_muldivdf3.o _arm_muldivsf3.o _arm_mulsf3.o \
	    _arm_negdf2.o _arm_negsf2.o _arm_cmpdf2.o _arm_cmpsf2.o \
	    _arm_fixdfsi.o _arm_fixsfsi.o _arm_fixunsdfsi.o _arm_fixunssfsi.o \
	    _arm_truncdfsf2.o _arm_unorddf2.o _arm_unordsf2.o \
	    _fixdfdi.o _fixsfdi.o _fixunsdfdi.o _fixunssfdi.o \
	    _powidf2.o _powisf2.o 2>/dev/null || true
	@cd obj/libgccx && $(ARMLD) -r *.o -o $(TOPDIR)/rt_aeabi.o && \
	    arm-none-eabi-strip --strip-debug $(TOPDIR)/rt_aeabi.o

# ---------- host-side TCC (reference / experiments) ----------
host:
	cd $(TCCSRC) && ./configure --prefix=$(TOPDIR)/host-tcc >/dev/null && \
	    make -j$$(nproc) >/dev/null && make install >/dev/null
	@echo "==> host TCC at $(HOSTTCC)"

test: tcc.elf rt_core.o rt_math.o rt_svc.o rt_aeabi.o
	python3 tests/harness.py

obj:
	mkdir -p obj

clean:
	rm -rf obj tcc.elf rt_core.o rt_svc.o rt_aeabi.o rt_math.o
	rm -f $(TCCSRC)/config.h

# Rebuild and copy the flat deployment directory (no subfolders - the
# calculator does not support them).  Only code.c is TCC-compiled on the
# calculator; the runtime is prebuilt (rt_core.o) and linked by TCC.
deploy: tcc.elf rt_core.o rt_svc.o rt_aeabi.o rt_math.o
	@mkdir -p ../primetcc.hpappdir
	@rm -f ../primetcc.hpappdir/hp_rt.c ../primetcc.hpappdir/hp_gfx.c \
	    ../primetcc.hpappdir/hp_input.c ../primetcc.hpappdir/hp_math.c \
	    ../primetcc.hpappdir/hp_string.c
	@cp tcc.elf calc/main.py hp/prime.h hp/stdbool.h rt_core.o rt_svc.o rt_aeabi.o rt_math.o \
	    rt/hp_gfx.h rt/hp_input.h rt/hp_math.h rt/hp_string.h rt/hp_fonts.h \
	    rt/hp_sys.h rt/hp_fixmath.h rt/hp_random.h rt/hp_codec.h rt/hp_gui.h \
	    ../primetcc.hpappdir/
	@echo "==> deployed to ../primetcc.hpappdir/"

.PHONY: all host test clean deploy
