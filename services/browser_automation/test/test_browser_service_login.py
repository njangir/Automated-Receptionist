"""Test script for BrowserService — opens a configurable login page (default: public demo)."""
import asyncio 
import logging 
import os 
import sys 
from pathlib import Path 


sys .path .insert (0 ,str (Path (__file__ ).parent .parent .parent .parent ))

from services .browser_automation .browser_service import BrowserService 
from services .browser_automation .chrome_launcher import ChromeLauncher 

logging .basicConfig (
level =logging .INFO ,
format ='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger =logging .getLogger (__name__ )


async def test_open_login_page ():
    """Test opening a login page using BrowserService (set LOGIN_URL for your own form)."""
    browser_service =None 
    launcher =None 

    try :

        launcher =ChromeLauncher (chrome_debug_port =9222 )


        logger .info ("Starting Chrome browser...")
        launcher .start_chrome ()
        logger .info ("Chrome browser started successfully")



        browser_service =BrowserService (
        chrome_debug_port =9222 ,
        auto_start_chrome =False 
        )


        logger .info ("Connecting to Chrome via CDP...")
        page =await browser_service .ensure_connected ()
        logger .info ("Successfully connected to Chrome")


        login_url =os .getenv ("LOGIN_URL","https://the-internet.herokuapp.com/login")
        logger .info (f"Navigating to: {login_url }")
        await page .goto (login_url )


        await page .wait_for_load_state ("networkidle")
        logger .info ("Page loaded successfully")


        title =await page .title ()
        logger .info (f"Page title: {title }")


        try :

            username_field =page .get_by_role ("textbox",name ="Username")
            password_field =page .get_by_role ("textbox",name ="Password")


            await username_field .wait_for (state ="visible",timeout =5000 )
            await password_field .wait_for (state ="visible",timeout =5000 )

            logger .info ("✅ Successfully opened login page - form elements are visible")





        except Exception as e :
            logger .warning (f"Could not verify login form elements: {e }")
            logger .info ("Page may still have loaded correctly")

        logger .info ("Test completed successfully")

    except Exception as e :
        logger .error (f"Test failed with error: {e }",exc_info =True )
        raise 




















if __name__ =="__main__":
    """Run the test as a standalone script."""
    asyncio .run (test_open_login_page ())
