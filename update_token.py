import datetime
import json
import tokgen


#Update token if not already updated
while True:
    tokfile = open('accesstoken.json', 'r')
    tokcont = json.load(tokfile)
    if tokcont['date']!=datetime.datetime.now().strftime("%d/%m/%Y"):
        tokfile.close()
        tokgen.main()
    else:
        tokfile.close()
        break
