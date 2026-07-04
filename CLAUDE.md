# RULES

1. run E2E at the end of the list of tasks, to make sure we speed up
2. high fedility design translation, if any feature is missing design you prompt to user. align kouji-ui like we did in ./projects/preesm 
3. use kouji-ui components, if they dont match check ./projects/kouji-ui implement/fix and release then continue
4. always try to run parallel work with sub agents and workflows max 3 in parallel
5. implement DDD modular style code with best practices. separate of features per folders. dont implement DDD at its fullest just feature per folder and hexagonal
6. check ./projects/preesm for deployment: use its render config file as template
