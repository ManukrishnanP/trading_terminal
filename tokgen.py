
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib
import urllib.parse
import requests
import webbrowser
import datetime
import json
f = open('secrets.json', 'r')
secrets = json.load(f)
f.close()
def main():


    class MyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            global secrets
            
            # Parse the URL and query parameters
            parsed_path = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_path.query)

            # Retrieve the 'code' parameter
            token = query_params.get('code', [''])[0]
            print(token)
            

            headers = {
                'Accept': 'application/json'
            }


            url = 'https://api.upstox.com/v2/login/authorization/token'
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            data = {
                'code': token,
                'client_id': secrets['client-id'],
                'client_secret': secrets['client-secret'],
                'redirect_uri': 'http://localhost:2000/',
                'grant_type': 'authorization_code',
            }

            print(data)

            reppy = requests.post(url, headers=headers, data=data)
            fc = {'date' : datetime.datetime.now().strftime("%d/%m/%Y"), "access_token" : reppy.json()['access_token']}
            print(reppy.json())

            myfile = open('accesstoken.json', 'w+')
            json.dump(fc, myfile, indent=1)
            myfile.close() 
            


            # Construct the response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Write the HTML response
            self.wfile.write(f"<html><body>You can close this tab.</body></html>".encode('utf-8'))

            import sys
            sys.exit()

    # Set up the server
    server_address = ('', 2000)  # Serve on port 8000
    httpd = HTTPServer(server_address, MyHandler)




    url = f'https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={secrets["client-id"]}&redirect_uri=http%3A%2F%2Flocalhost%3A2000%2F'
    webbrowser.open(url=url)



    print("Serving on port 2000...")
    httpd.serve_forever()

if __name__=="__main__":
    main()
