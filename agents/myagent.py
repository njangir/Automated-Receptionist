import asyncio 
import json 
import logging 
import os 
import platform 
import re 
import sys 
from datetime import datetime 
from pathlib import Path 
from typing import Optional 

import httpx 
import sounddevice as sd 


if platform .system ()=="Windows":

    if hasattr (sys .stdout ,'reconfigure'):
        try :
            sys .stdout .reconfigure (encoding ='utf-8')
        except Exception :
            pass 
    if hasattr (sys .stderr ,'reconfigure'):
        try :
            sys .stderr .reconfigure (encoding ='utf-8')
        except Exception :
            pass 

from livekit import rtc 
from livekit .agents import (
Agent ,
AgentServer ,
AgentSession ,
JobContext ,
JobProcess ,
RunContext ,
ToolError ,
inference ,
cli ,
function_tool ,
room_io ,
)
from livekit .plugins import noise_cancellation ,silero ,openai ,elevenlabs ,deepgram 
from livekit .plugins .turn_detector .multilingual import MultilingualModel 


logging .basicConfig (
level =logging .INFO ,
format ='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger =logging .getLogger ("agent")


from services .browser_automation .browser_service import BrowserService 

from services .call_logger import CallLogger 

try :
    from services .browser_automation .profile_service import ProfileService 
except ImportError :
    from services .browser_automation .file_loader import load_profile_service 
    profile_service_module =load_profile_service ()
    if profile_service_module :
        ProfileService =profile_service_module .ProfileService 
    else :
        ProfileService =None 
        logger .warning ("ProfileService not available - profile features disabled")

try :
    from services .browser_automation .portfolio_service import PortfolioService 
except ImportError :
    from services .browser_automation .file_loader import load_portfolio_service 
    portfolio_service_module =load_portfolio_service ()
    if portfolio_service_module :
        PortfolioService =portfolio_service_module .PortfolioService 
    else :
        PortfolioService =None 
        logger .warning ("PortfolioService not available - portfolio features disabled")


root_dir =Path (__file__ ).parent .parent 
from services .config_loader import load_config 
load_config (root_dir )



client_code =os .getenv ("CLIENT_CODE")
phone_number =os .getenv ("PHONE_NUMBER")
name =os .getenv ("NAME")




def safe_print (msg ,file =sys .stdout ):
    """Print message with encoding error handling for Windows console."""
    try :
        print (msg ,file =file )
    except UnicodeEncodeError :


        safe_msg =msg .replace ('✅','[OK]').replace ('⚠️','[WARN]').replace ('❌','[ERROR]')
        try :
            print (safe_msg ,file =file )
        except UnicodeEncodeError :

            print (msg .encode ('utf-8',errors ='replace').decode ('utf-8',errors ='replace'),file =file )

if not client_code or not phone_number or not name :
    warning_msg =(
    f"⚠️  Environment variables not fully set - "
    f"CLIENT_CODE: {client_code }, PHONE_NUMBER: {phone_number }, NAME: {name }"
    )
    logger .warning (warning_msg )
    safe_print (warning_msg ,file =sys .stderr )
else :
    info_msg =(
    f"✅ Environment variables loaded - "
    f"CLIENT_CODE: {client_code }, PHONE_NUMBER: {phone_number }, NAME: {name }"
    )
    logger .info (info_msg )
    safe_print (info_msg )


if platform .system ()=="Windows":
    import gc 

    gc .set_threshold (700 ,10 ,10 )

    os .environ .setdefault ("PYTHONUNBUFFERED","1")


    try :
        import psutil 
        try :
            p =psutil .Process ()
            p .nice (psutil .BELOW_NORMAL_PRIORITY_CLASS )
            logger .info ("Set process priority to BELOW_NORMAL for Windows")
        except (psutil .AccessDenied ,AttributeError ):

            pass 
    except ImportError :

        pass 


def get_performance_profile ()->dict :
    """
    Get performance profile settings based on environment variable.
    
    Returns:
        Dictionary with performance settings:
        - stt_model: STT model name
        - llm_max_tokens: Maximum tokens for LLM responses
        - preemptive_generation: Whether to use preemptive generation
        - noise_cancellation: Whether to enable noise cancellation
        - turn_detection: Turn detection mode ("disabled", "optional", "required")
        - stt_endpointing: Endpointing timeout in ms
        - llm_temperature: LLM temperature setting
    """
    profile_name =os .getenv ("PERFORMANCE_PROFILE","balanced").lower ()


    profiles ={
    "low":{
    "stt_model":"nova-2",
    "llm_max_tokens":100 ,
    "preemptive_generation":False ,
    "noise_cancellation":False ,
    "turn_detection":"disabled",
    "stt_endpointing":300 ,
    "llm_temperature":0.7 ,
    },
    "balanced":{
    "stt_model":"nova-3",
    "llm_max_tokens":150 ,
    "preemptive_generation":True ,
    "noise_cancellation":True ,
    "turn_detection":"optional",
    "stt_endpointing":500 ,
    "llm_temperature":0.7 ,
    },
    "high":{
    "stt_model":"nova-3",
    "llm_max_tokens":200 ,
    "preemptive_generation":True ,
    "noise_cancellation":True ,
    "turn_detection":"optional",
    "stt_endpointing":500 ,
    "llm_temperature":0.7 ,
    },
    }


    if profile_name not in profiles :
        logger .warning (f"Unknown performance profile '{profile_name }', using 'balanced'")
        profile_name ="balanced"

    profile =profiles [profile_name ].copy ()


    if os .getenv ("STT_MODEL"):
        profile ["stt_model"]=os .getenv ("STT_MODEL")
        logger .info (f"Overriding STT model with STT_MODEL={profile ['stt_model']}")

    if os .getenv ("LLM_MAX_TOKENS"):
        try :
            profile ["llm_max_tokens"]=int (os .getenv ("LLM_MAX_TOKENS"))
            logger .info (f"Overriding LLM max_tokens with LLM_MAX_TOKENS={profile ['llm_max_tokens']}")
        except ValueError :
            logger .warning (f"Invalid LLM_MAX_TOKENS value: {os .getenv ('LLM_MAX_TOKENS')}")

    if os .getenv ("PREEMPTIVE_GENERATION"):
        profile ["preemptive_generation"]=os .getenv ("PREEMPTIVE_GENERATION").lower ()=="true"
        logger .info (f"Overriding preemptive_generation with PREEMPTIVE_GENERATION={profile ['preemptive_generation']}")

    if os .getenv ("NOISE_CANCELLATION_ENABLED"):
        profile ["noise_cancellation"]=os .getenv ("NOISE_CANCELLATION_ENABLED").lower ()=="true"
        logger .info (f"Overriding noise_cancellation with NOISE_CANCELLATION_ENABLED={profile ['noise_cancellation']}")

    if os .getenv ("TURN_DETECTION_ENABLED"):
        turn_enabled =os .getenv ("TURN_DETECTION_ENABLED").lower ()=="true"
        profile ["turn_detection"]="optional"if turn_enabled else "disabled"
        logger .info (f"Overriding turn_detection with TURN_DETECTION_ENABLED={turn_enabled }")

    logger .info (f"Using performance profile: {profile_name .upper ()} - "
    f"STT: {profile ['stt_model']}, "
    f"LLM tokens: {profile ['llm_max_tokens']}, "
    f"Preemptive: {profile ['preemptive_generation']}, "
    f"Noise cancellation: {profile ['noise_cancellation']}, "
    f"Turn detection: {profile ['turn_detection']}")

    return profile 


class Assistant (Agent ):
    def __init__ (self ,context_vars :Optional [dict ]=None )->None :
        """
        Initialize the Assistant agent with optional context variables.
        
        Args:
            context_vars: Dictionary containing 'name', 'phone_number', and 'client_code'
        """

        instructions_template ="""Tum ek helpful male voice assistant ho aur tumhara naam MyAgent hai. Tum hinglish mein baat karte ho (hindi + english mix). User {name} jo phone number {phone_number} ke saath hai, woh tumse voice ke through baat kar raha hai, chahe tum conversation ko text samjho. Tum "Example Securities" naam ki ek demo stock broking firm ke representative ke roop mein kaam karte ho (yeh ek template hai — apne brand ke hisaab se badal sakte ho).
            User ka client code {client_code} hai. Tum users ki queries mein unki madad karte ho apne tools se jaise ki user bank details, user portfolio details, IPO updates, cashout help, account opening procedure, aur baaki general queries.
            Tumhare responses bahut short aur concise hone chahiye (ek ya do sentences mein). Koi complex formatting, punctuation, emojis, asterisks, ya koi bhi symbols use mat karo.
            Tum curious, friendly ho, aur tumhare andar sense of humor hai.
            
            IMPORTANT: Agar user conversation ke dauran apna naam, client code, ya phone number de, toh store_user_info tool use karke yeh information save kar do. Yeh information personalized service dene ke liye zaroori hai.
            
            CALL ENDING: Jab conversation complete ho jaye, user ka kaam ho jaye, ya user call end karna chahe, toh end_call_and_disconnect tool use karo. Is tool ko use karte waqt:
            - Summary: Conversation ka brief summary do (1-2 sentences)
            - Rating: Call ki quality ka rating do (1-5, jahan 5 sabse best hai)
            - Duration: Call ki duration seconds mein (agar automatically calculate karna hai toh skip kar sakte ho)
            IMPORTANT: Yeh tool automatically caller ko inform karega ki call end ho rahi hai, phir phone rakh kar, call details log karega, aur agent ko stop karega."""


        if context_vars :
            instructions =instructions_template .format (**context_vars )
            logger .info (f"Agent instructions formatted with context: name={context_vars .get ('name')}, phone_number={context_vars .get ('phone_number')}, client_code={context_vars .get ('client_code')}")
        else :

            fallback_vars ={
            "name":name or "User",
            "phone_number":phone_number or "unknown",
            "client_code":client_code or "unknown"
            }
            instructions =instructions_template .format (**fallback_vars )
            logger .warning ("No context_vars provided, using environment variables as fallback")

        super ().__init__ (instructions =instructions )


        self ._client_code =context_vars .get ("client_code")if context_vars else client_code 
        self ._name =context_vars .get ("name")if context_vars else name 
        self ._phone_number =context_vars .get ("phone_number")if context_vars else phone_number 


        self ._collected_info ={
        "name":self ._name ,
        "client_code":self ._client_code ,
        "phone_number":self ._phone_number 
        }


        self ._call_start_time =datetime .now ()
        self ._call_ended =False 
        self ._disconnect_reason =None 


        self ._call_logger =CallLogger ()


        chrome_debug_port =int (os .getenv ("CHROME_DEBUG_PORT","9222"))
        self ._browser_service :Optional [BrowserService ]=None 
        self ._chrome_debug_port =chrome_debug_port 

    async def on_enter (self )->None :
        """
        Called when the agent enters the session.
        This initiates the conversation with a greeting.
        If required information is missing, it will be collected first.
        """

        try :
            call_id =self ._call_logger .start_call (
            client_name =self ._name or "User",
            phone_number =self ._phone_number or "unknown",
            client_code =self ._client_code or "unknown"
            )
            logger .info (f"Started call logging with call_id: {call_id }")
        except Exception as e :
            logger .warning (f"Failed to start call logging: {e }",exc_info =True )


        pick_service_url =os .getenv ("PICK_SERVICE_URL","")
        if not pick_service_url :
            logger .warning ("PICK_SERVICE_URL not configured, skipping pick request")
        else :
            logger .info (f"Sending pick request to: {pick_service_url }")
            try :
                async with httpx .AsyncClient (timeout =10.0 )as client :
                    pick_response =await client .post (
                    pick_service_url ,
                    json ={}
                    )
                    pick_response .raise_for_status ()


                    try :
                        response_data =pick_response .json ()
                        if response_data .get ('data')!='OK':
                            logger .error (f"Pick request returned unexpected response: {response_data }")
                            return 
                        logger .info (f"Pick request successful. Status: {pick_response .status_code }, Response: {response_data }")
                    except (ValueError ,KeyError ):

                        logger .info (f"Pick request successful. Status: {pick_response .status_code }")


                    await asyncio .sleep (1.0 )
                    logger .info ("Pick request completed, proceeding with greeting")

            except httpx .TimeoutException :
                logger .error (f"Pick request timed out for {pick_service_url }")
                return 
            except httpx .HTTPStatusError as e :
                logger .error (f"Pick request failed with status {e .response .status_code }: {e .response .text }")
                return 
            except Exception as e :
                logger .error (f"Failed to send pick request: {e }",exc_info =True )
                return 


        if hasattr (self ,'session')and self .session :
            logger .info ("=== TESTING TRANSCRIPTION CAPTURE ===")


            try :
                @self .session .on ("conversation_item_added")
                def on_conversation_item (item ):
                    """Capture and log transcriptions from conversation events."""
                    try :

                        if not hasattr (item ,'item'):
                            logger .debug ("[TRANSCRIPTION] No item.item found in event")
                            return 

                        conversation_item =item .item 


                        text_content =None 
                        if hasattr (conversation_item ,'content'):
                            content =conversation_item .content 
                            if isinstance (content ,list ):

                                text_content =' '.join (str (c )for c in content if c )
                            elif content :
                                text_content =str (content )


                        if not text_content and hasattr (conversation_item ,'text_content'):
                            text_content =conversation_item .text_content 

                        if not text_content :
                            logger .debug ("[TRANSCRIPTION] No text content found in conversation item")
                            return 


                        speaker ="user"
                        if hasattr (conversation_item ,'role'):
                            role =conversation_item .role 
                            if role =="assistant":
                                speaker ="agent"
                            elif role =="user":
                                speaker ="user"


                        timestamp =None 
                        if hasattr (item ,'created_at'):
                            try :
                                from datetime import datetime 

                                timestamp =datetime .fromtimestamp (item .created_at )
                            except :
                                pass 
                        elif hasattr (conversation_item ,'created_at'):
                            try :
                                from datetime import datetime 
                                timestamp =datetime .fromtimestamp (conversation_item .created_at )
                            except :
                                pass 


                        self ._call_logger .log_transcription (
                        text =text_content ,
                        speaker =speaker ,
                        timestamp =timestamp 
                        )

                        logger .info (f"[TRANSCRIPTION] Captured {speaker } transcript: {text_content [:50 ]}...")

                    except Exception as e :
                        logger .error (f"[TRANSCRIPTION] Error capturing transcription: {e }",exc_info =True )

                logger .info ("[TRANSCRIPTION TEST] conversation_item_added event handler registered")
            except Exception as e :
                logger .error (f"[TRANSCRIPTION TEST] Failed to register conversation_item_added handler: {e }",exc_info =True )


            try :
                if hasattr (self .session ,'history'):
                    logger .info (f"[TRANSCRIPTION TEST] session.history exists: {type (self .session .history )}")
                    logger .info (f"[TRANSCRIPTION TEST] session.history class: {self .session .history .__class__ .__name__ }")


                    history_attrs =[attr for attr in dir (self .session .history )if not attr .startswith ('_')]
                    logger .info (f"[TRANSCRIPTION TEST] history attributes: {history_attrs }")


                    if hasattr (self .session .history ,'items'):
                        items_list =list (self .session .history .items )
                        logger .info (f"[TRANSCRIPTION TEST] history.items count: {len (items_list )}")

                        for idx ,item in enumerate (items_list ):
                            logger .info (f"[TRANSCRIPTION TEST] history.items[{idx }]: type={type (item )}, class={item .__class__ .__name__ }")
                            item_attrs =[x for x in dir (item )if not x .startswith ('_')]
                            logger .info (f"[TRANSCRIPTION TEST] history.items[{idx }] attributes: {item_attrs }")


                            for attr in ['text','content','role','from','timestamp','speaker']:
                                if hasattr (item ,attr ):
                                    try :
                                        value =getattr (item ,attr )
                                        logger .info (f"[TRANSCRIPTION TEST] history.items[{idx }].{attr } = {value }")
                                    except :
                                        pass 
                    else :
                        logger .warning ("[TRANSCRIPTION TEST] history.items does not exist")


                    for method in ['to_dict','to_list','get_items','get_messages']:
                        if hasattr (self .session .history ,method ):
                            try :
                                result =getattr (self .session .history ,method )()
                                logger .info (f"[TRANSCRIPTION TEST] history.{method }() returned: {type (result )}")
                                if isinstance (result ,(list ,dict ))and len (str (result ))<500 :
                                    logger .info (f"[TRANSCRIPTION TEST] history.{method }() content: {result }")
                            except Exception as e :
                                logger .debug (f"[TRANSCRIPTION TEST] history.{method }() error: {e }")
                else :
                    logger .warning ("[TRANSCRIPTION TEST] session.history does not exist")
            except Exception as e :
                logger .error (f"[TRANSCRIPTION TEST] Error accessing history: {e }",exc_info =True )


            session_attrs =[attr for attr in dir (self .session )if not attr .startswith ('_')and 'transcript'in attr .lower ()]
            if session_attrs :
                logger .info (f"[TRANSCRIPTION TEST] Found transcript-related session attributes: {session_attrs }")
                for attr in session_attrs :
                    try :
                        value =getattr (self .session ,attr )
                        logger .info (f"[TRANSCRIPTION TEST] session.{attr } = {type (value )}")
                    except :
                        pass 

            logger .info ("=== TRANSCRIPTION CAPTURE TEST SETUP COMPLETE ===")
            logger .info ("[TRANSCRIPTION TEST] Note: Console logs (stdout/stderr) may also contain STT/LLM transcripts")
            logger .info ("[TRANSCRIPTION TEST] Check agent log files in log directory for existing transcripts")
            logger .info ("[TRANSCRIPTION TEST] ============================================================")
            logger .info ("[TRANSCRIPTION TEST] TESTING SUMMARY:")
            logger .info ("[TRANSCRIPTION TEST] 1. Registered conversation_item_added event handler")
            logger .info ("[TRANSCRIPTION TEST] 2. Tested session.history access")
            logger .info ("[TRANSCRIPTION TEST] 3. Checked for transcript-related session attributes")
            logger .info ("[TRANSCRIPTION TEST] ============================================================")
            logger .info ("[TRANSCRIPTION TEST] During call, watch for [TRANSCRIPTION TEST] logs to see:")
            logger .info ("[TRANSCRIPTION TEST] - If conversation_item_added events fire (real-time capture)")
            logger .info ("[TRANSCRIPTION TEST] - What data is available in event items")
            logger .info ("[TRANSCRIPTION TEST] - If session.history contains transcripts (polling approach)")
            logger .info ("[TRANSCRIPTION TEST] ============================================================")


        missing_info =[]
        if not self ._name or self ._name .lower ()in ["user","unknown"]:
            missing_info .append ("name")
        if not self ._client_code or self ._client_code .lower ()=="unknown":
            missing_info .append ("client_code")

        if missing_info :
            logger .info (f"Missing information detected: {missing_info }. Will collect from user.")

            missing_items =", ".join (missing_info )
            collect_instruction =(
            f"Yeh information missing hai: {missing_items }. "
            f"User se politely ek ek karke yeh information pucho. "
            f"Pehle unhe greet karo aur phir pehli missing item ke liye pucho. "
            f"Jab saari information collect ho jaye, toh store_user_info tool use karke save kar do. "
            f"Hinglish mein friendly aur conversational tareeke se baat karo."
            )
            await self .session .generate_reply (instructions =collect_instruction )
        else :

            first_name =self ._name .split ()[0 ]if self ._name else "User"
            greeting_instruction =f"Conversation shuru karte waqt user ko greet karo. Bolo 'Hello, ha {first_name } Ji!' aur phir reply ka wait karo."
            logger .info (f"Agent entering session, generating greeting for user: {first_name }")
            await self .session .generate_reply (instructions =greeting_instruction )

    @function_tool 
    async def store_user_info (
    self ,
    context :RunContext ,
    name :Optional [str ]=None ,
    client_code :Optional [str ]=None ,
    phone_number :Optional [str ]=None 
    )->str :
        """
        Conversation ke dauran collect ki gayi user information ko store karo.
        Jab user apna naam, client code, ya phone number de, tab yeh tool use karo.
        
        Args:
            name: User ka full name
            client_code: User ka client code
            phone_number: User ka phone number
        """
        updated =[]
        if name and name .lower ()not in ["user","unknown"]:
            self ._collected_info ["name"]=name 
            self ._name =name 
            updated .append ("name")
            logger .info (f"Stored user name: {name }")

        if client_code and client_code .lower ()!="unknown":
            self ._collected_info ["client_code"]=client_code 
            self ._client_code =client_code 
            updated .append ("client_code")
            logger .info (f"Stored client code: {client_code }")

        if phone_number and phone_number .lower ()!="unknown":
            self ._collected_info ["phone_number"]=phone_number 
            self ._phone_number =phone_number 
            updated .append ("phone_number")
            logger .info (f"Stored phone number: {phone_number }")

        if updated :
            return f"Successfully store ho gaya: {', '.join (updated )}"
        else :
            return "Koi valid information store karne ke liye nahi hai. Kripya name, client_code, ya phone_number provide karo."

    def _get_rating_text (self ,numeric :int )->str :
        """Convert numeric rating to text."""
        rating_map ={
        1 :"Poor",
        2 :"Fair",
        3 :"Neutral",
        4 :"Good",
        5 :"Excellent"
        }
        return rating_map .get (numeric ,"Neutral")

    async def _generate_mood_from_conversation (self )->str :
        """
        Generate mood from conversation history using LLM.
        
        Returns:
            Mood string (e.g., "happy", "neutral", "frustrated"), or "neutral" as fallback
        """
        mood ="neutral"
        try :

            conversation_history =self ._call_logger .get_conversation_history ()
            if not conversation_history :
                logger .warning ("No conversation history available for mood generation")
                return mood 


            if not hasattr (self ,'session')or not self .session :
                logger .warning ("Session not available for mood generation")
                return mood 

            if not hasattr (self .session ,'llm')or not self .session .llm :
                logger .warning ("LLM not available in session for mood generation")
                return mood 


            metadata =await self ._call_logger .generate_call_metadata (
            self .session .llm ,
            conversation_history 
            )
            mood =metadata .get ("mood","neutral")
            logger .info (f"Generated mood from conversation: {mood }")

        except Exception as e :
            logger .warning (f"Failed to generate mood: {e }, using default 'neutral'",exc_info =True )

        return mood 

    @function_tool 
    async def end_call_and_disconnect (
    self ,
    context :RunContext ,
    summary :str ,
    rating :int ,
    duration_seconds :Optional [float ]=None 
    )->str :
        """
        Call end karne ke liye use karo jab conversation complete ho jaye.
        Yeh tool caller ko inform karega, phir phone rakh kar, call details log karega, aur phir agent ko stop karega.
        
        Args:
            summary: Call ka summary (1-2 sentences mein)
            rating: Call ki rating (1-5, jahan 5 sabse best hai)
            duration_seconds: Call ki duration seconds mein (agar nahi diya toh automatically calculate hoga)
        """
        try :

            if duration_seconds is None :
                duration_seconds =(datetime .now ()-self ._call_start_time ).total_seconds ()


            rating_dict ={
            "numeric":rating ,
            "text":self ._get_rating_text (rating )
            }


            try :
                if hasattr (self ,'session')and self .session :
                    goodbye_message ="Thank you for calling! Aapka din shubh rahe."
                    logger .info ("Sending pre-disconnect message to caller")
                    speech_handle =await self .session .say (
                    goodbye_message ,
                    allow_interruptions =False 
                    )
                    await speech_handle .wait_for_playout ()
                    logger .info ("Pre-disconnect message delivered successfully")
            except Exception as e :
                logger .warning (f"Failed to send pre-disconnect message: {e }",exc_info =True )



            webhook_url =(os .getenv ("END_CALL_WEBHOOK")or "").strip ()
            if webhook_url :
                logger .info (f"Sending call end webhook to: {webhook_url }")
                try :
                    async with httpx .AsyncClient (timeout =10.0 )as client :
                        webhook_response =await client .post (webhook_url )
                        webhook_response .raise_for_status ()
                        logger .info (f"Webhook sent successfully. Status: {webhook_response .status_code }")
                except httpx .TimeoutException :
                    logger .error (f"Webhook request timed out for {webhook_url }")
                except httpx .HTTPStatusError as e :
                    logger .error (
                    f"Webhook request failed with status {e .response .status_code }: {e .response .text }"
                    )
                except Exception as e :
                    logger .error (f"Failed to send webhook: {e }",exc_info =True )
            else :
                logger .info ("END_CALL_WEBHOOK not set; skipping call-end webhook")


            mood =await self ._generate_mood_from_conversation ()


            logger .info (f"Recording call details: summary={summary [:50 ]}..., rating={rating }, mood={mood }, duration={duration_seconds :.2f}s")
            try :
                log_file_path =self ._call_logger .end_call (
                summary =summary ,
                mood =mood ,
                rating =rating_dict ,
                status ="completed",
                save_to_firebase =True 
                )
                if log_file_path :
                    logger .info (f"Call details saved to: {log_file_path }")
                else :
                    logger .warning ("Call logger returned None - call may not have been started")
            except Exception as e :
                logger .error (f"Failed to record call details: {e }",exc_info =True )



            server_port =int (os .getenv ("SERVER_PORT",os .getenv ("AGENT_MANAGER_PORT","8000")))
            server_host =os .getenv ("SERVER_HOST",os .getenv ("AGENT_MANAGER_HOST","127.0.0.1"))

            if server_host =="0.0.0.0":
                server_host ="127.0.0.1"
            api_server_url =f"http://{server_host }:{server_port }"
            stop_endpoint =f"{api_server_url }/stop"

            logger .info (f"Sending stop request to: {stop_endpoint }")
            try :
                async with httpx .AsyncClient (timeout =10.0 )as client :
                    stop_response =await client .post (stop_endpoint )
                    stop_response .raise_for_status ()
                    logger .info (f"Stop request sent successfully. Status: {stop_response .status_code }")
            except httpx .TimeoutException :
                logger .error (f"Stop request timed out for {stop_endpoint }")
            except httpx .HTTPStatusError as e :
                logger .error (f"Stop request failed with status {e .response .status_code }: {e .response .text }")
            except Exception as e :
                logger .error (f"Failed to send stop request: {e }",exc_info =True )


            self ._call_ended =True 
            self ._disconnect_reason ="llm_initiated"

            return f"Call successfully end ho gaya. Summary: {summary [:50 ]}..., Rating: {rating }/5, Duration: {duration_seconds :.1f}s"

        except Exception as e :
            error_msg =f"Error: Call end karne mein problem aayi: {str (e )}"
            logger .error (error_msg ,exc_info =True )
            return error_msg 

    async def on_exit (self )->None :
        """
        Called when the agent exits the session.
        Ensures call log is saved if not already saved.
        """
        logger .info ("Agent session ended")


        if hasattr (self ,'_call_logger')and self ._call_logger and self ._call_logger .call_data :
            try :
                logger .info ("Saving call log on agent exit")


                mood =self ._call_logger .call_data .get ("mood")
                if not mood :
                    mood =await self ._generate_mood_from_conversation ()
                    logger .info (f"Generated mood on exit: {mood }")

                self ._call_logger .end_call (
                summary =self ._call_logger .call_data .get ("summary")or "Call ended",
                mood =mood ,
                rating =self ._call_logger .call_data .get ("rating"),
                status ="completed",
                save_to_firebase =True 
                )
            except Exception as e :
                logger .error (f"Failed to save call log on exit: {e }",exc_info =True )

    async def disconnect_call (self ,reason :str ="agent_initiated")->None :
        """
        Manually disconnect the call. Can be called from tools or agent logic.
        
        Args:
            reason: Reason for disconnection (e.g., "task_completed", "user_requested", "error")
        """
        logger .info (f"Disconnecting call. Reason: {reason }")
        self ._call_ended =True 
        self ._disconnect_reason =reason 
        if hasattr (self ,'session')and self .session :
            await self .session .shutdown ()

    async def _get_browser_service (self )->BrowserService :
        """Get or create browser service instance."""
        if self ._browser_service is None :

            chrome_user_data_dir =os .getenv ("CHROME_USER_DATA_DIR")
            chrome_executable_path =os .getenv ("CHROME_EXECUTABLE_PATH")
            chrome_auto_start =os .getenv ("CHROME_AUTO_START","true").lower ()=="true"

            self ._browser_service =BrowserService (
            chrome_debug_port =self ._chrome_debug_port ,
            auto_start_chrome =chrome_auto_start ,
            chrome_user_data_dir =chrome_user_data_dir ,
            chrome_executable_path =chrome_executable_path 
            )
        return self ._browser_service 

    @function_tool 
    async def get_user_bank_details (self ,context :RunContext )->str :
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
                return "Error: ProfileService available nahi hai. Kripya ensure karo ki module installed ya downloaded hai."

            browser_service =await self ._get_browser_service ()
            page =await browser_service .ensure_connected ()


            profile_service =ProfileService (page )
            result =await profile_service .get_user_bank_details (self ._client_code )

            return result 

        except Exception as e :
            error_msg =f"Error: Bank details retrieve karne mein fail ho gaya: {str (e )}"
            logger .error (error_msg ,exc_info =True )
            return error_msg 

    def llm_node (self ,*args ,**kwargs ):
        """
        Create LLM inference node. Required by LiveKit's voice agent pipeline.
        Delegates to parent class implementation.
        
        Returns:
            LLM inference node
        """
        return super ().llm_node (*args ,**kwargs )

    def transcription_node (self ,*args ,**kwargs ):
        """
        Create transcription node. Required by LiveKit's voice agent pipeline.
        Delegates to parent class implementation.
        
        Returns:
            Transcription node
        """
        return super ().transcription_node (*args ,**kwargs )

    @function_tool 
    async def get_user_portfolio (self ,context :RunContext )->str :
        """
        User ke portfolio details get karo.
        Yeh tool system se user ke portfolio holdings fetch karta hai aur unhe structured table format mein return karta hai.
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
                return "Error: PortfolioService available nahi hai. Kripya ensure karo ki module installed ya downloaded hai."

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

server =AgentServer ()


def prewarm (proc :JobProcess ):
    """Prewarm function to load VAD model before agent sessions."""

    profile =get_performance_profile ()




    proc .userdata ["vad"]=silero .VAD .load ()
    proc .userdata ["performance_profile"]=profile 
    logger .info (f"VAD loaded with performance profile: {os .getenv ('PERFORMANCE_PROFILE','balanced')}")


server .setup_fnc =prewarm 


@server .rtc_session ()
async def my_agent (ctx :JobContext ):
    """
    RTC session entrypoint. Creates the agent with context variables from environment.
    This follows LiveKit's recommended pattern for passing user context to agents.
    """


    context_variables ={
    "name":name ,
    "phone_number":phone_number ,
    "client_code":client_code 
    }


    if not all ([name ,phone_number ,client_code ]):
        logger .error (
        f"Missing required context variables - name: {name }, "
        f"phone_number: {phone_number }, client_code: {client_code }"
        )

        context_variables ={
        "name":name or "User",
        "phone_number":phone_number or "unknown",
        "client_code":client_code or "unknown"
        }

    logger .info (
    f"Creating agent session with context - name: {context_variables ['name']}, "
    f"phone_number: {context_variables ['phone_number']}, "
    f"client_code: {context_variables ['client_code']}"
    )


    profile =ctx .proc .userdata .get ("performance_profile")
    if profile is None :
        profile =get_performance_profile ()
        ctx .proc .userdata ["performance_profile"]=profile 



    stt_instance =deepgram .STT (
    model =profile ["stt_model"],
    language ="hi",
    endpointing_ms =profile ["stt_endpointing"],
    )



    turn_detector =None 
    turn_detection_mode =profile ["turn_detection"]

    if turn_detection_mode =="disabled":
        logger .info ("Turn detector disabled by performance profile (low mode)")
    elif turn_detection_mode in ["optional","required"]:
        try :
            turn_detector =MultilingualModel ()
            logger .info ("Turn detector initialized successfully")
        except RuntimeError as e :
            if "Could not find file"in str (e )or "model_q8.onnx"in str (e )or "languages.json"in str (e ):
                logger .warning (
                f"Turn detector models not found: {e }. "
                "Agent will run without turn detection. "
                "Models can be downloaded via LiveKit CLI if needed."
                )
                turn_detector =None 
            else :
                logger .warning (f"Failed to initialize turn detector: {e }. Agent will run without turn detection.")
                turn_detector =None 
        except Exception as e :
            logger .warning (f"Unexpected error initializing turn detector: {e }. Agent will run without turn detection.")
            turn_detector =None 

    session =AgentSession (
    stt =stt_instance ,
    llm =openai .LLM (
    model ="gpt-4o-mini",
    temperature =profile ["llm_temperature"]
    ),
    tts =elevenlabs .TTS (
    model ="eleven_multilingual_v2",
    voice_id ="8sNEbeluclbr4u71MPb0",
    language ="hi"
    ),



    turn_detection =turn_detector ,
    vad =ctx .proc .userdata ["vad"],
    preemptive_generation =profile ["preemptive_generation"]
    )


    audio_input_device_id =None 
    audio_output_device_id =None 

    try :
        input_device_name =os .getenv ("AUDIO_INPUT_DEVICE_ID","").strip ()
        output_device_name =os .getenv ("AUDIO_OUTPUT_DEVICE_ID","").strip ()

        if input_device_name :

            devices =sd .query_devices ()
            for i ,device in enumerate (devices ):
                if device ["name"]==input_device_name and device ["max_input_channels"]>0 :
                    audio_input_device_id =i 
                    logger .info (f"Using audio input device: {input_device_name } (index: {i })")
                    break 
            if audio_input_device_id is None :
                logger .warning (f"Audio input device '{input_device_name }' not found, using system default")

        if output_device_name :

            devices =sd .query_devices ()
            for i ,device in enumerate (devices ):
                if device ["name"]==output_device_name and device ["max_output_channels"]>0 :
                    audio_output_device_id =i 
                    logger .info (f"Using audio output device: {output_device_name } (index: {i })")
                    break 
            if audio_output_device_id is None :
                logger .warning (f"Audio output device '{output_device_name }' not found, using system default")
    except ImportError :
        logger .warning ("sounddevice not available, using system default audio devices")
    except Exception as e :
        logger .warning (f"Error configuring audio devices: {e }, using system defaults")


    agent =Assistant (context_vars =context_variables )



    if profile ["noise_cancellation"]:
        audio_input_kwargs ={
        "noise_cancellation":lambda params :noise_cancellation .BVCTelephony ()
        if params .participant .kind ==rtc .ParticipantKind .PARTICIPANT_KIND_SIP 
        else noise_cancellation .BVC (),
        }
    else :

        audio_input_kwargs ={
        "noise_cancellation":None ,
        }
        logger .info ("Noise cancellation disabled by performance profile")


    if audio_input_device_id is not None :
        audio_input_kwargs ["device_id"]=audio_input_device_id 

    audio_input_options =room_io .AudioInputOptions (**audio_input_kwargs )


    audio_output_kwargs ={}
    if audio_output_device_id is not None :
        audio_output_kwargs ["device_id"]=audio_output_device_id 

    audio_output_options =room_io .AudioOutputOptions (**audio_output_kwargs )if audio_output_kwargs else None 


    room_options_kwargs ={
    "audio_input":audio_input_options ,
    }
    if audio_output_options is not None :
        room_options_kwargs ["audio_output"]=audio_output_options 

    await session .start (
    agent =agent ,
    room =ctx .room ,
    room_options =room_io .RoomOptions (**room_options_kwargs ),
    )


    async def on_participant_disconnected (participant :rtc .RemoteParticipant ):
        """Called when a participant disconnects from the room."""
        logger .info (f"Participant {participant .identity } disconnected from room {ctx .room .name }")
        agent ._call_ended =True 
        agent ._disconnect_reason ="participant_disconnected"

    async def on_room_disconnected ():
        """Called when the room is disconnected."""
        logger .info (f"Room {ctx .room .name } disconnected")
        agent ._call_ended =True 
        agent ._disconnect_reason ="room_disconnected"


    ctx .room .on ("participant_disconnected",on_participant_disconnected )
    ctx .room .on ("disconnected",on_room_disconnected )

    async def send_call_webhook ():
        """
        Send HTTP webhook when call ends.
        This is called on shutdown to notify external systems about call completion.
        Also ensures call is saved to file and Firebase if not already saved.
        """
        webhook_url =""
        try :

            call_duration =(datetime .now ()-agent ._call_start_time ).total_seconds ()

            webhook_url =(os .getenv ("END_CALL_WEBHOOK")or "").strip ()
            if webhook_url :
                async with httpx .AsyncClient (timeout =10.0 )as client :
                    response =await client .post (webhook_url )
                    response .raise_for_status ()
                    logger .info (
                    f"Webhook sent successfully. Status: {response .status_code }, "
                    f"Response: {response .text [:200 ]}"
                    )
            else :
                logger .info ("END_CALL_WEBHOOK not set; skipping shutdown webhook")



            if hasattr (agent ,'_call_logger')and agent ._call_logger :

                if agent ._call_logger .call_data :
                    try :
                        logger .info ("Call ended via shutdown callback, saving call log")


                        mood =agent ._call_logger .call_data .get ("mood")
                        if not mood and hasattr (agent ,'_generate_mood_from_conversation'):
                            try :
                                mood =await agent ._generate_mood_from_conversation ()
                                logger .info (f"Generated mood in shutdown callback: {mood }")
                            except Exception as e :
                                logger .warning (f"Failed to generate mood in shutdown: {e }, using default")
                                mood ="neutral"
                        elif not mood :
                            mood ="neutral"



                        agent ._call_logger .end_call (
                        summary =agent ._call_logger .call_data .get ("summary")or "Call ended via shutdown",
                        mood =mood ,
                        rating =agent ._call_logger .call_data .get ("rating"),
                        status ="completed",
                        save_to_firebase =True 
                        )
                        logger .info ("Call log saved successfully during shutdown")
                    except Exception as e :
                        logger .error (f"Failed to save call log in shutdown callback: {e }",exc_info =True )
                else :

                    logger .debug ("Call log already saved or call was never started")

        except httpx .TimeoutException :
            logger .error (f"Webhook request timed out for {webhook_url }")

            if hasattr (agent ,'_call_logger')and agent ._call_logger and agent ._call_logger .call_data :
                try :

                    mood =agent ._call_logger .call_data .get ("mood")
                    if not mood and hasattr (agent ,'_generate_mood_from_conversation'):
                        try :
                            mood =await agent ._generate_mood_from_conversation ()
                        except Exception :
                            mood ="neutral"
                    elif not mood :
                        mood ="neutral"

                    agent ._call_logger .end_call (
                    summary ="Call ended (webhook timeout)",
                    mood =mood ,
                    status ="completed",
                    save_to_firebase =True 
                    )
                except Exception as e :
                    logger .error (f"Failed to save call log after webhook timeout: {e }",exc_info =True )
        except httpx .HTTPStatusError as e :
            logger .error (f"Webhook request failed with status {e .response .status_code }: {e .response .text }")

            if hasattr (agent ,'_call_logger')and agent ._call_logger and agent ._call_logger .call_data :
                try :

                    mood =agent ._call_logger .call_data .get ("mood")
                    if not mood and hasattr (agent ,'_generate_mood_from_conversation'):
                        try :
                            mood =await agent ._generate_mood_from_conversation ()
                        except Exception :
                            mood ="neutral"
                    elif not mood :
                        mood ="neutral"

                    agent ._call_logger .end_call (
                    summary ="Call ended (webhook error)",
                    mood =mood ,
                    status ="completed",
                    save_to_firebase =True 
                    )
                except Exception as e2 :
                    logger .error (f"Failed to save call log after webhook error: {e2 }",exc_info =True )
        except Exception as e :
            logger .error (f"Failed to send webhook: {e }",exc_info =True )

            if hasattr (agent ,'_call_logger')and agent ._call_logger and agent ._call_logger .call_data :
                try :

                    mood =agent ._call_logger .call_data .get ("mood")
                    if not mood and hasattr (agent ,'_generate_mood_from_conversation'):
                        try :
                            mood =await agent ._generate_mood_from_conversation ()
                        except Exception :
                            mood ="neutral"
                    elif not mood :
                        mood ="neutral"

                    agent ._call_logger .end_call (
                    summary ="Call ended (error)",
                    mood =mood ,
                    status ="completed",
                    save_to_firebase =True 
                    )
                except Exception as e2 :
                    logger .error (f"Failed to save call log after error: {e2 }",exc_info =True )


    ctx .add_shutdown_callback (send_call_webhook )

    await ctx .connect ()


if __name__ =="__main__":
    cli .run_app (server )
