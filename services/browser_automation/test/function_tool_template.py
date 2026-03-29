"""
Template for creating function tools that use browser automation services.

This template shows the core structure of a function tool based on the pattern
used in agents/myagent.py. Use this as a reference when creating new function tools.

Key Components:
1. @function_tool decorator
2. async function with context: RunContext parameter
3. Optional wait message with speech
4. Input validation (e.g., client_code)
5. Service availability check
6. Browser service setup
7. Service instantiation and method call
8. Result processing/validation
9. Error handling

NOTE: This is a template file. The example functions below will show linting
warnings because the service imports are commented out. When you use this template,
uncomment and add the necessary imports for your specific service.
"""

from typing import Optional 
from livekit .agents import RunContext ,function_tool 
from playwright .async_api import Page 











import logging 
logger =logging .getLogger (__name__ )






@function_tool 
async def your_function_tool_name (
self ,
context :RunContext ,



)->str :
    """
    Tool ka description yahan likho.
    Yeh tool kya karta hai, iska clear description do.
    
    Args:
        context: RunContext object (required by LiveKit)
        # Add descriptions for your custom parameters
        # param1: Description of param1
        # param2: Description of param2
    
    Returns:
        str: Result message ya data jo tool return karega
    """





    wait_message ="बस एक मिनट, processing कर रही हूँ।"

    speech_handle =await self .session .say (
    wait_message ,
    allow_interruptions =False 
    )
    await speech_handle .wait_for_playout ()





    if not self ._client_code or self ._client_code .lower ()=="unknown":
        return "Error: Client code available nahi hai. Kripya pehle apna client code provide karo."
















    try :

        browser_service =await self ._get_browser_service ()


        page =await browser_service .ensure_connected ()



































        return "Success: Tool executed successfully"




    except Exception as e :
        error_msg =f"Error: Operation fail ho gaya: {str (e )}"
        logger .error (error_msg ,exc_info =True )
        return error_msg 






@function_tool 
async def get_user_bank_details_example (
self ,
context :RunContext 
)->str :
    """
    User ke bank details get karo.
    Yeh tool system se user ke bank account details fetch karta hai.
    """

    wait_message ="बस एक मिनट, आपके बैंक डिटेल्स check कर रही हूँ।"

    speech_handle =await self .session .say (
    wait_message ,
    allow_interruptions =False 
    )
    await speech_handle .wait_for_playout ()


    if not self ._client_code or self ._client_code .lower ()=="unknown":
        return "Error: Client code available nahi hai. Kripya pehle apna client code provide karo."

    try :

        if ProfileService is None :
            return "Error: ProfileService available nahi hai."


        browser_service =await self ._get_browser_service ()
        page =await browser_service .ensure_connected ()


        profile_service =ProfileService (page )
        result =await profile_service .get_user_bank_details (self ._client_code )


        return result 

    except Exception as e :
        error_msg =f"Error: Bank details retrieve karne mein fail ho gaya: {str (e )}"
        logger .error (error_msg ,exc_info =True )
        return error_msg 






@function_tool 
async def get_user_portfolio_example (
self ,
context :RunContext 
)->str :
    """
    User ke portfolio details get karo.
    Yeh tool system se user ke portfolio holdings fetch karta hai.
    """
    wait_message ="बस एक मिनट, आपके portfolio check कर रही हूँ।"

    speech_handle =await self .session .say (
    wait_message ,
    allow_interruptions =False 
    )
    await speech_handle .wait_for_playout ()

    if not self ._client_code or self ._client_code .lower ()=="unknown":
        return "Error: Client code available nahi hai. Kripya pehle apna client code provide karo."

    try :
        if PortfolioService is None :
            return "Error: PortfolioService available nahi hai."

        browser_service =await self ._get_browser_service ()
        page =await browser_service .ensure_connected ()

        portfolio_service =PortfolioService (page )
        result =await portfolio_service .get_user_portfolio (self ._client_code )


        if '|'in result and 'Scrip Name'in result :
            return result 
        elif result .startswith ("Error:"):
            return result 
        else :
            return f"Error: Invalid table format mila. Data: {result [:200 ]}"

    except Exception as e :
        error_msg =f"Error: Portfolio retrieve karne mein fail ho gaya: {str (e )}"
        logger .error (error_msg ,exc_info =True )
        return error_msg 






@function_tool 
async def login_example (
self ,
context :RunContext ,
username :Optional [str ]=None ,
password :Optional [str ]=None ,
login_type :Optional [str ]=None 
)->str :
    """
    Login karo backoffice system mein.
    
    Args:
        username: Login username
        password: Login password
        login_type: Login type option value
    """
    wait_message ="बस एक मिनट, login process kar rahi hoon।"

    speech_handle =await self .session .say (
    wait_message ,
    allow_interruptions =False 
    )
    await speech_handle .wait_for_playout ()

    try :
        if LoginService is None :
            return "Error: LoginService available nahi hai."

        browser_service =await self ._get_browser_service ()
        page =await browser_service .ensure_connected ()

        login_service =LoginService (page )

        success =await login_service .login (
        username =username ,
        password =password ,
        login_type =login_type 
        )

        if success :
            return "Login form successfully filled. Ready for submission."
        else :
            return "Error: Login form fill karne mein problem aayi."

    except Exception as e :
        error_msg =f"Error: Login process fail ho gaya: {str (e )}"
        logger .error (error_msg ,exc_info =True )
        return error_msg 





"""
1. DECORATOR: Always use @function_tool decorator
2. SIGNATURE: Must have 'self' (if class method) and 'context: RunContext'
3. RETURN TYPE: Always returns str
4. WAIT MESSAGE: Optional but recommended for long operations
5. VALIDATION: Check required inputs (client_code, etc.)
6. SERVICE CHECK: Verify service is available (for dynamic imports)
7. BROWSER SERVICE: Get via self._get_browser_service() method
8. PAGE: Get via browser_service.ensure_connected()
9. SERVICE INSTANCE: Create with page: YourService(page)
10. METHOD CALL: Call async method: await service.method(params)
11. RESULT PROCESSING: Validate and format result as needed
12. ERROR HANDLING: Always wrap in try-except with logging
13. LOGGING: Use logger.error() with exc_info=True for debugging
"""
