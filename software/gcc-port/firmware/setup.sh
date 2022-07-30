#!/bin/bash
# chmod 755 setup.sh
# sudo ./setup.sh pru_iep.patch

TOOLCHAIN=pru-elf-2022.05.amd64
TOOLS_DIR=tools

# 1. Create a directory to host the tools
echo "1. Create a tools directory"
mkdir -p $TOOLS_DIR
echo "2. Change to tools directory"
cd $TOOLS_DIR

# 2. Install the cross-compiler toolchain by downloading and untar gnupru release
echo "3. Downloading the cross-compiler toolchain..."
wget -r -tries=2 https://github.com/dinuxbg/gnupru/releases/download/2022.05/$TOOLCHAIN.tar.xz --output-document=gcc-port -o log 
echo "4. Untar'ing the cross-compiler toolchain..."
tar -xf gcc-port
echo "5. Deleting toolchain archive..."
rm -rf gcc-port

# 3. Install the PRU software support packages from the pru-software-support-package (branch name: linux-4.19-rproc)
echo "6. Cloning PRU software support packages (linux-4.19-rproc branch)"
git clone -b linux-4.19-rproc https://github.com/dinuxbg/pru-software-support-package.git

# 4. Add PRU gcc and binutils to your PATH
echo "7. Adding PRU GCC supports to path..."
export PRU_GCC_BIN=$PWD/$TOOLCHAIN/bin
echo "#PRU GCC  supports" >> ~/.bashrc
echo "export PRU_GCC=$PRU_GCC_BIN" >> ~/.bashrc
echo "export PRU_SUPPORT=$PWD/pru-software-support-package" >> ~/.bashrc
echo 'export PATH=$PATH:$PRU_GCC' >> ~/.bashrc
export PS1=$PS1:fix
source ~/.bashrc

# 5. Patch PRU software support packages
echo "8. Patching PRU software support packages..."
cd ../
sed -i -e "s/\(volatile __far\).*/\/\/patch>>/" $PWD/$TOOLS_DIR/pru-software-support-package/include/am335x/pru_iep.h
sed -i -e "/\/\/patch>>/r $1" $PWD/$TOOLS_DIR/pru-software-support-package/include/am335x/pru_iep.h

# 6. Compile
echo "9. Compiling..."
make

# 7. Exit
echo "10. Done!"
