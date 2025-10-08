# Установите необходимые зависимости для сборки
sudo apt install build-essential autoconf linux-headers-$(uname -r) git

# Клонируйте репозиторий
git clone https://github.com/linuxwacom/input-wacom.git

# Перейдите в директорию
cd input-wacom

# Если у вас Linux 2.6.30 или новее
./autogen.sh
./configure
make
sudo make install

# Перезагрузите систему или перезапустите драйвер
sudo modprobe -r wacom
sudo modprobe wacom

