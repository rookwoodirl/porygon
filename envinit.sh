/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
echo >> /Users/christian/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> /Users/christian/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# this is for chess gif
brew install cairo
brew install --cask caido

# run the session boot
bash reboot.sh