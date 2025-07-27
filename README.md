# Adobe-Hackathon-Round-1a

command 1 : 

docker build --platform linux/amd64 -t mysolutionname:adobeindiahackathonRound1A .

command 2 : 

docker run --rm -v "${PWD}/input:/app/input" -v "${PWD}/output:/app/output" --network none mysolutionname:adobeindiahackathonRound1A