
###############
# TODO Work will commence on this after MAY 2021 
# RESTful server 
# Currently focused on notification_server.py, get_candles.py, and notification_scripts
###############



from flask import Flask, request
from flask_restx import Resource, Api, reqparse, fields # , abort, marshal_with (needed to formatting output)

# Flask web server application which handles website and communication with trading bot server and 
