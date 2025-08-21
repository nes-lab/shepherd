# dev-script for faster rebuilding (compared to ansible)
cd /opt/shepherd/software/firmware/pru0-shepherd-fw/
# EMU
sudo make clean
make TYPE=EMU
sudo make install TYPE=EMU
# HRV
sudo make clean
make TYPE=HRV
sudo make install TYPE=HRV
#
cd /opt/shepherd/software/firmware/pru1-shepherd-fw/
# GPIO
sudo make clean
make
sudo make install
#
cd /opt/shepherd/software/firmware/pru0-programmer/
# PRG SWD
sudo make clean
make TYPE=SWD
sudo make install TYPE=SWD
# PROG SBW
sudo make clean
make TYPE=SBW
sudo make install TYPE=SBW
#
cd /opt/shepherd/software/
