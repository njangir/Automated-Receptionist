"""Demo/mock responses when BROWSER_USE_MOCK_DATA is enabled (no live portal automation)."""
import json 
import logging 
import os 
from typing import Any ,Dict 

from services .path_utils import get_demo_data_dir 

logger =logging .getLogger (__name__ )

_cached :Dict [str ,Any ]|None =None 


def _load_file ()->Dict [str ,Any ]:
    global _cached 
    if _cached is not None :
        return _cached 
    path =get_demo_data_dir ()/"mock_browser_responses.json"
    if not path .exists ():
        logger .warning ("mock_browser_responses.json not found at %s",path )
        _cached ={}
        return _cached 
    try :
        with open (path ,"r",encoding ="utf-8")as f :
            _cached =json .load (f )
    except (json .JSONDecodeError ,OSError )as e :
        logger .error ("Failed to load mock browser responses: %s",e )
        _cached ={}
    return _cached 


def use_mock_browser_data ()->bool :
    return os .getenv ("BROWSER_USE_MOCK_DATA","true").lower ()=="true"


def get_mock_bank_details ()->str :
    data =_load_file ()
    return data .get (
    "bank_details",
    "Bank details (demo): edit demo/mock_browser_responses.json",
    )


def get_mock_portfolio_markdown ()->str :
    data =_load_file ()
    return data .get (
    "portfolio_markdown",
    "| Demo | |\n| --- | --- |\n| (empty) | |",
    )
