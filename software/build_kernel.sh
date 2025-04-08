# dev-script for faster rebuilding (compared to ansible)
sudo modprobe -rf shepherd
sudo modprobe -rf shepherd
#
cd /opt/shepherd/software/kernel-module/src/
#
make clean
make
sudo make install
#
cd /opt/shepherd/software/
#
sudo modprobe -a shepherd
