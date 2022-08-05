#!/bin/bash
# sudo chmod +x run.sh
# ./run.sh 

TOOLCHAIN=pru-elf-2022.05.amd64
TOOLS_DIR=tools

export PRU_GCC=$PWD/$TOOLS_DIR/$TOOLCHAIN/bin
export PRU_SUPPORT=$PWD/$TOOLS_DIR/pru-software-support-package
export PATH="$PATH:$PRU_GCC"

make
