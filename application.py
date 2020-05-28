import os
import requests, json, random, re

from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from flask_googlemaps import GoogleMaps
from flask_googlemaps import Map
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") # a requirement for flask session
if not app.secret_key:
    raise RuntimeError("SECRET_KEY not set")

gmaps_api = os.environ.get("GMAPS_API")
if not gmaps_api:
    raise RuntimeError("GMAPS_API not set")

ow_api = os.environ.get("OW_API")
if not ow_api:
    raise RuntimeError("OW_API not set")

GoogleMaps(app, key=gmaps_api)

# opening a JSON containing all of the cities and storing name, country and coordinates in a list of dicts

with open("city.list.json", "r", encoding="utf-8") as cities:
    x = json.load(cities)
    city_list = [None] * len(x)

    for i in range(len(x)):
        city_list[i] = {}
        city_list[i]["name"] = x[i]["name"]
        city_list[i]["state"] = x[i]["state"]
        city_list[i]["country"] = x[i]["country"]
        city_list[i]["coord"] = x[i]["coord"]
        city_list[i]["id"] = x[i]["id"]

# just to change the display of the unit str itself, the different values are got from different API calls
units_main = {"metric":{"temp":"C", "speed":"m/s"}, "imperial":{"temp":"F", "speed":"mph"}}

# as OW API provides wind direction in degs, this and the directions function turn them into cardinal directions
wind_dir = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"] 

def directions(deg):
    x = deg/22.5 + 0.5
    if x >= 16:
        x = 1

    return wind_dir[int(round(x))-1]

# accepts format "metric" or "imperial" and city ID (from grad variable) to make a call to OW API
def weather(format, grad):
    id = grad["id"]
    ow_response = requests.get(f"http://api.openweathermap.org/data/2.5/weather?id={id}&appid={ow_api}&units={format}")
    ow = ow_response.json()
    try:
        ow["wind"]["dir"] = directions(ow["wind"]["deg"]) # API sometimes doesn't provide the wind direction and raises a KeyError
    except KeyError:
        ow["wind"]["dir"] = ""
    
    return ow

# sets the icon path depending on weather conditions indicated by id code
def iconify(id):
    if id == 800:
        icon = "/static/icons/clear.png"
    elif id in range(200, 233):
        icon = "/static/icons/thunder.png"
    elif id in range(300, 322):
        icon = "/static/icons/drizzle.png"
    elif id in range(500, 532):
        icon = "/static/icons/rain.png"
    elif id in range(600, 623):
        icon = "/static/icons/snow.png"
    elif id in range(700, 782):
        icon = "/static/icons/haze.png"
    else:
        icon = "/static/icons/clouds.png"

    return icon

# returns a google maps object given arguments grad (which holds coordinates info) and icon 
def mapify(grad, icon):
    karta = Map(
            identifier = "karta",
            lat = grad["coord"]["lat"],
            lng = grad["coord"]["lon"],
            markers = [
                {
                    "icon": icon,
                    "lat": grad["coord"]["lat"],
                    "lng": grad["coord"]["lon"]
                }],
            zoom = 5,
            maptype="HYBRID",
            maptype_control = False,
            fullscreen_control = False,
            scale_control = False,
            style="height: 100%; width: 100%; margin: 0px"
        )
    
    return karta

# makes a call to REST countries API; takes country info from the grad variable
def countrify(grad):
    zemlja = grad["country"]
    c_response = requests.get(f"https://restcountries.eu/rest/v2/alpha/{zemlja}")
    country = c_response.json()

    return country

# takes the search query and returns a list of dict items (from city_list) which match it (per get_close_matches)
def searchify(query):
    r = [item for item in city_list if fuzz.token_set_ratio(re.sub("[^a-zA-Z ]+", "", query), re.sub("[^a-zA-Z ]+", "", item["name"])) > 95] # the regex notation is just to strip all non-alphanumeric (excluding space) characters
       
    if len(r) == 0:
        return None
       
    return r
    
# combined routes that route /, /freedom and /about
@app.route("/")
@app.route("/<tag>")
def index(tag=None):
    if tag == "about":
        return render_template("about.html")

    elif session.get("grad") == None: #metric and imperial implementation block

        if tag == "freedom":
            session["format"] = "imperial"
        else:
            session["format"] = "metric"

        grad = random.choice(city_list)
        ow = weather(session["format"], grad)

        id = ow["weather"][0]["id"]
        icon = iconify(id)
        karta = mapify(grad, icon)
        country = countrify(grad)

        session["grad"] = grad
        session["ow"] = ow
        session["units"] = units_main
        session["icon"] = icon
        session["country"] = country
        
        if tag == "freedom":
            return render_template("freedom.html", grad = grad, ow = ow, units = units_main, karta = karta, country = country)
        else:
            return render_template("index.html", grad = grad, ow = ow, units = units_main, karta = karta, country = country)

    elif tag == "freedom" and session.get("format") == "imperial":
        session.clear()
        return redirect("/freedom")
    
    elif tag == None and session.get("format") == "metric":
        session.clear()
        return redirect("/")
        
    elif tag == "freedom" and session.get("format") == "metric":
        session["format"] = "imperial"
    elif tag == None and session.get("format") == "imperial":
        session["format"] = "metric"

    grad = session.get("grad", None)
    ow = weather(session["format"], grad)
    units = session.get("units", None)
    country = session.get("country", None)
    icon = session.get("icon", None)
    karta = mapify(grad, icon)    

    if tag == "freedom":
        return render_template("freedom.html", grad = grad, ow = ow, units = units, karta = karta, country = country)
    else:
        return render_template("index.html", grad = grad, ow = ow, units = units, karta = karta, country = country)

# if query returns only one and exact result, you're directly redirected to its page; otherwise you get a list of results 
@app.route("/search", methods=["POST"])
def search():
    query = request.form.get("search").capitalize()
    result = searchify(query)   

    if result and len(result) == 1:
        grad = result[0]
        session["grad"] = grad
        ow = weather(session["format"], grad)
        session["ow"] = ow
        session["units"] = units_main
        session["icon"] = iconify(ow["weather"][0]["id"])
        session["country"] = countrify(grad)
        
        if session["format"] == "imperial":
            session["format"] = "metric"
            return redirect("/freedom")
        
        if session["format"] == "metric":
            session["format"] = "imperial"
            return redirect("/")

    else:
        return render_template("result.html", result = result)

# after selecting the desired result you're redirected to its page based on its id
@app.route("/result/<mark>")
def result(mark=None):
    id = int(mark)
    grad = [city for city in city_list if city["id"] == id]
    grad = grad[0]

    session["grad"] = grad
    ow = weather(session["format"], grad)
    session["ow"] = ow
    session["units"] = units_main
    session["icon"] = iconify(ow["weather"][0]["id"])
    session["country"] = countrify(grad)
    session["format"] = "imperial"

    return redirect("/")

    