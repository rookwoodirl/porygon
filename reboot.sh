echo rebooting porygon...
killall python3
git checkout main
git pull
python3 -m pip install -r requirements.txt
echo rebooting...
python3 porygon.py &