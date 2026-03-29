"""Test script for LoginService - tests the login function."""
import asyncio 
import logging 
import sys 
from pathlib import Path 


sys .path .insert (0 ,str (Path (__file__ ).parent .parent .parent .parent ))

from services .browser_automation .browser_service import BrowserService 
from services .browser_automation .chrome_launcher import ChromeLauncher 
from services .browser_automation .login_service import LoginService 

logging .basicConfig (
level =logging .INFO ,
format ='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger =logging .getLogger (__name__ )


async def test_login_service ():
    """Test the LoginService login function."""
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


        logger .info ("Creating LoginService instance...")
        login_service =LoginService (page )



        logger .info ("Calling LoginService.login()...")
        login_success =await login_service .login ()

        if login_success :
            logger .info ("✅ LoginService.login() completed successfully")
            logger .info ("Login form has been filled (not submitted)")
        else :
            logger .warning ("⚠️ LoginService.login() returned False")


        logger .info ("Keeping browser open for 10 seconds for visual verification...")
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
    asyncio .run (test_login_service ())
