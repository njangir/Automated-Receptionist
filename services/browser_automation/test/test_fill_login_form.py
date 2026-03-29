"""Test script for filling dummy credentials on a configurable login page."""
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


async def test_fill_login_form ():
    """Test filling dummy login credentials in the login form."""
    browser_service =None 
    launcher =None 

    try :

        launcher =ChromeLauncher (chrome_debug_port =9222 )


        logger .info ("Ensuring Chrome browser is running...")
        launcher .ensure_chrome_running (port =9222 ,auto_start =True )
        logger .info ("Chrome browser is ready")



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


        logger .info ("Waiting for login form elements...")
        username_field =page .get_by_role ("textbox",name ="Username")
        password_field =page .get_by_role ("textbox",name ="Password")

        await username_field .wait_for (state ="visible",timeout =10000 )
        await password_field .wait_for (state ="visible",timeout =10000 )
        logger .info ("Login form elements are visible")


        dummy_username ="dummy_user@example.com"
        logger .info (f"Filling username field with: {dummy_username }")
        await username_field .click ()
        await username_field .fill (dummy_username )
        logger .info ("✅ Username field filled")


        dummy_password ="dummy_password_123"
        logger .info ("Filling password field with dummy password")
        await password_field .click ()
        await password_field .fill (dummy_password )
        logger .info ("✅ Password field filled")


        username_value =await username_field .input_value ()
        password_value =await password_field .input_value ()

        logger .info (f"Verified - Username field contains: {username_value }")
        logger .info ("Verified - Password field contains: [hidden]")

        if username_value ==dummy_username and password_value ==dummy_password :
            logger .info ("✅ Successfully filled login form with dummy credentials")
        else :
            logger .warning ("⚠️ Form fields may not have been filled correctly")


        logger .info ("Keeping browser open for 10 seconds for visual verification...")
        logger .info ("NOTE: Form will NOT be submitted - only fields are filled")
        await asyncio .sleep (10 )

        logger .info ("Test completed successfully")

    except Exception as e :
        logger .error (f"Test failed with error: {e }",exc_info =True )
        raise 

    finally :

        if browser_service :
            try :
                logger .info ("Closing BrowserService connection...")
                await browser_service .close (stop_chrome =False )
            except Exception as e :
                logger .warning (f"Error closing BrowserService: {e }")


        if launcher :
            try :
                logger .info ("Stopping Chrome browser...")
                launcher .stop_chrome ()
                logger .info ("Chrome browser stopped")
            except Exception as e :
                logger .warning (f"Error stopping Chrome: {e }")


if __name__ =="__main__":
    """Run the test as a standalone script."""
    asyncio .run (test_fill_login_form ())
