import requests
import json
from bs4 import BeautifulSoup
import urllib3
import urllib.parse
import re
import random
import os
from ai_solver import configure_keys

# Disable SSL warnings if the server has certificate issues
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
print("--- MAKAUT Exam Login ---")
USERNAME = input("Enter your Username / Roll No: ").strip()
PASSWORD = input("Enter your Password: ").strip()
# ---------------------

# --- AI API Keys ---
# Securely load from local environment file (so they aren't pushed to GitHub)
env_path = os.path.join(os.path.dirname(__file__), "web", ".env.local")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k] = v

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
CEREBRAS_KEY = os.environ.get("CEREBRAS_API_KEY", "")
configure_keys(GEMINI_KEY, GROQ_KEY, CEREBRAS_KEY)
print("[+] AI Ensemble ready (Gemini + Groq + Cerebras)\n")
# -------------------

# Setup session and URLs
session = requests.Session()
base_url = "https://makauttest3.ucanapply.com"
get_url = f"{base_url}/onlineexam/public/"
post_url = f"{base_url}/onlineexam/public/livewire/message/login-page"

# Set standard User-Agent (A Computer Browser) to avoid the device check error
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html, application/xhtml+xml, application/xml",
    "Accept-Language": "en-US,en;q=0.9"
}

def main():
    print("[*] Fetching initial login page to gather tokens and Livewire states...")

    # 1. Make the GET request to grab tokens and Livewire data
    try:
        response = session.get(get_url, headers=headers, verify=False)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[-] Failed to load initial page: {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract CSRF token from the <meta> tag
    csrf_token_meta = soup.find('meta', {'name': 'csrf-token'})
    if not csrf_token_meta:
        print("[-] Could not find CSRF token in HTML.")
        return
    csrf_token = csrf_token_meta['content']
    
    # Extract Livewire Initial Data from the login div
    login_div = soup.find('div', class_='login-form1')
    if not login_div:
        print("[-] Could not find the Livewire login div. The page structure might have changed.")
        return

    try:
        initial_data_str = login_div['wire:initial-data']
        livewire_data = json.loads(initial_data_str)
    except (KeyError, json.JSONDecodeError):
        print("[-] Failed to parse Livewire initial data.")
        return

    # 2. Construct the exact Livewire POST Payload
    payload = {
        "fingerprint": livewire_data["fingerprint"],
        "serverMemo": livewire_data["serverMemo"],
        "updates": [
            {
                "type": "syncInput",
                "payload": {
                    "name": "password",
                    "value": PASSWORD
                }
            },
            {
                "type": "syncInput",
                "payload": {
                    "name": "username",
                    "value": USERNAME
                }
            },
            {
                "type": "callMethod",
                "payload": {
                    "method": "submit",
                    "params": []
                }
            }
        ]
    }

    # 3. Set Headers required for the Livewire POST
    post_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "text/html, application/xhtml+xml",
        "Content-Type": "application/json",
        "X-Livewire": "true",
        "X-CSRF-TOKEN": csrf_token,
        "Origin": base_url,
        "Referer": get_url
    }

    print("[*] Sending Login POST request...")

    # 4. Send the POST Request
    try:
        post_response = session.post(post_url, json=payload, headers=post_headers, verify=False)
        post_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[-] POST request failed: {e}")
        return

    response_json = post_response.json()
    
    # Handle "Already Logged In" case
    if response_json.get('serverMemo', {}).get('data', {}).get('alreadySession') == 'Y':
        print("[!] Active session detected. Attempting to destroy previous session...")
        
        # Update serverMemo with the response from the first POST
        new_memo = response_json.get('serverMemo', {})
        payload['serverMemo']['htmlHash'] = new_memo.get('htmlHash', payload['serverMemo']['htmlHash'])
        payload['serverMemo']['checksum'] = new_memo.get('checksum', payload['serverMemo']['checksum'])
        for k, v in new_memo.get('data', {}).items():
            payload['serverMemo']['data'][k] = v
            
        # Update the payload updates to click "Destroy & Proceed"
        payload['updates'] = [
            {
                "type": "callMethod",
                "payload": {
                    "method": "$set",
                    "params": ["destroy", "Y"]
                }
            },
            {
                "type": "callMethod",
                "payload": {
                    "method": "submit",
                    "params": []
                }
            }
        ]
        
        # Send the second POST request
        print("[*] Sending Destroy & Proceed request...")
        try:
            post_response = session.post(post_url, json=payload, headers=post_headers, verify=False)
            post_response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[-] Second POST request failed: {e}")
            return
            
        response_json = post_response.json()

    if 'effects' in response_json and 'redirect' in response_json['effects']:
        dashboard_url = response_json['effects']['redirect']
        print(f"\n[+] Login Successful! Redirecting to: {dashboard_url}")
        
        # 5. Fetch the Dashboard Page using the same authenticated session
        print("[*] Fetching dashboard data...\n")
        dash_response = session.get(dashboard_url, headers=headers, verify=False)
        dash_soup = BeautifulSoup(dash_response.text, 'html.parser')
        
        # Verify login by finding the Welcome message
        welcome_msg = dash_soup.find('div', class_='alert-success')
        if welcome_msg:
            clean_text = welcome_msg.text.replace('×', '').strip()
            print(f"--- {clean_text} ---")
        else:
            print("[-] Reached dashboard, but could not find the Welcome message.")
            
        # Extract and print the list of subjects
        print("\nList Of All Subjects:")
        subject_list = dash_soup.find_all('li', class_='list-group-item')
        if subject_list:
            for subject in subject_list:
                print(f"  > {subject.text.strip()}")
        else:
            print("  (No subjects found)")
            
        # 6. Fetch Active Papers
        print("\n[*] Checking for Active Papers...")
        active_papers_url = f"{base_url}/onlineexam/public/student/getActivePapper"
        active_headers = headers.copy()
        active_headers["X-Requested-With"] = "XMLHttpRequest"
        
        # Include X-XSRF-TOKEN header as required by Laravel AJAX
        xsrf_token_cookie = session.cookies.get('XSRF-TOKEN')
        if xsrf_token_cookie:
            active_headers["X-XSRF-TOKEN"] = urllib.parse.unquote(xsrf_token_cookie)

        try:
            active_response = session.get(active_papers_url, headers=active_headers, verify=False)
            active_response.raise_for_status()
            active_json = active_response.json()
            
            if 'html' in active_json:
                active_soup = BeautifulSoup(active_json['html'], 'html.parser')
                
                # Check for "No Paper Found"
                no_paper = active_soup.find(string=lambda s: s and 'No Paper Found' in s)
                if no_paper:
                    print("  [-] Status: No Paper Found.")
                else:
                    print("  [+] Active Paper(s) detected!")
                    
                    # Extract the paper link(s)
                    paper_links = active_soup.find_all('a', class_='list-group-item')
                    for paper in paper_links:
                        subject_title = paper.find('h5')
                        subject_name = subject_title.text.strip() if subject_title else "Unknown Subject"
                        paper_url = paper.get('href')
                        
                        if paper_url:
                            print(f"\n[*] Found Active Exam: {subject_name}")
                            print(f"[*] Navigating to exam instructions: {paper_url}")
                            
                            try:
                                # Fetch exam instruction page
                                instr_resp = session.get(paper_url, headers=headers, verify=False)
                                instr_resp.raise_for_status()
                                
                                # Extract Javascript data payload
                                paperID_match = re.search(r'paperID:\s*(\d+)', instr_resp.text)
                                paper_type_match = re.search(r'paper_type:\s*(\d+)', instr_resp.text)
                                start_date_match = re.search(r'start_date:\s*(\d+)', instr_resp.text)
                                crypt_name_match = re.search(r'crypt_name:\s*["\']([^"\']+)["\']', instr_resp.text)
                                
                                if paperID_match and paper_type_match and start_date_match and crypt_name_match:
                                    print("  [+] Extracted Exam start payload successfully!")
                                    start_payload = {
                                        "paperID": int(paperID_match.group(1)),
                                        "paper_type": int(paper_type_match.group(1)),
                                        "start_date": int(start_date_match.group(1)),
                                        "crypt_name": crypt_name_match.group(1)
                                    }
                                    
                                    # Send Start Exam Request
                                    start_exam_url = f"{base_url}/onlineexam/public/student/check-exam-started-invigilator"
                                    
                                    start_headers = headers.copy()
                                    start_headers["X-Requested-With"] = "XMLHttpRequest"
                                    
                                    xsrf_cookie = session.cookies.get('XSRF-TOKEN')
                                    if xsrf_cookie:
                                        start_headers["X-XSRF-TOKEN"] = urllib.parse.unquote(xsrf_cookie)
                                        
                                    print("  [*] Sending request to start the exam...")
                                    start_resp = session.post(start_exam_url, json=start_payload, headers=start_headers, verify=False)
                                    start_resp.raise_for_status()
                                    
                                    start_json = start_resp.json()
                                    if start_json.get("status") == True:
                                        next_url = start_json.get('url')
                                        print(f"  [+] Exam Started Successfully!")
                                        print(f"  [+] Next Exam URL: {next_url}")
                                        
                                        if next_url:
                                            print("  [*] Navigating to the actual exam paper...")
                                            exam_resp = session.get(next_url, headers=headers, verify=False)
                                            exam_resp.raise_for_status()
                                            
                                            print("  [+] Successfully loaded the exam page!")
                                            
                                            exam_soup = BeautifulSoup(exam_resp.text, 'html.parser')
                                            
                                            # Extract fresh CSRF token from the exam page just in case
                                            exam_csrf_meta = exam_soup.find('meta', {'name': 'csrf-token'})
                                            exam_csrf = exam_csrf_meta['content'] if exam_csrf_meta else csrf_token
                                            
                                            question_component = None
                                            # Find the Livewire component data for 'questionbutton'
                                            for el in exam_soup.find_all(attrs={"wire:initial-data": True}):
                                                try:
                                                    init_data = json.loads(el['wire:initial-data'])
                                                    if init_data.get('fingerprint', {}).get('name') == 'questionbutton':
                                                        question_component = init_data
                                                        break
                                                except:
                                                    continue
                                                    
                                            if question_component:
                                                print("  [*] Found 'questionbutton' Livewire component.")
                                                
                                                # Construct Livewire POST request to fetch the first question
                                                q_payload = {
                                                    "fingerprint": question_component["fingerprint"],
                                                    "serverMemo": question_component["serverMemo"],
                                                    "updates": [
                                                        {
                                                            "type": "callMethod",
                                                            "payload": {
                                                                "method": "loadQuestion",
                                                                "params": []
                                                            }
                                                        }
                                                    ]
                                                }
                                                
                                                q_url = f"{base_url}/onlineexam/public/livewire/message/questionbutton"
                                                
                                                q_headers = headers.copy()
                                                q_headers.update({
                                                    "Accept": "text/html, application/xhtml+xml",
                                                    "Content-Type": "application/json",
                                                    "X-Livewire": "true",
                                                    "X-CSRF-TOKEN": exam_csrf,
                                                    "Origin": base_url,
                                                    "Referer": next_url
                                                })
                                                
                                                # ====================================================
                                                # PHASE 1: COLLECT ALL QUESTIONS (no answering yet)
                                                # ====================================================
                                                print(f"\n{'='*60}")
                                                print(f"  PHASE 1: COLLECTING ALL QUESTIONS")
                                                print(f"{'='*60}")
                                                print("  [*] Fetching Question 1 and determining total questions...")
                                                try:
                                                    q_resp = session.post(q_url, json=q_payload, headers=q_headers, verify=False)
                                                    q_resp.raise_for_status()
                                                    q_json = q_resp.json()
                                                    
                                                    current_serverMemo = question_component["serverMemo"].copy()
                                                    new_memo = q_json.get('serverMemo', {})
                                                    if new_memo:
                                                        current_serverMemo['checksum'] = new_memo.get('checksum', current_serverMemo['checksum'])
                                                        current_serverMemo['htmlHash'] = new_memo.get('htmlHash', current_serverMemo['htmlHash'])
                                                        if 'data' in new_memo:
                                                            current_serverMemo['data'].update(new_memo['data'])
                                                    
                                                    total_pages = 1
                                                    all_questions = []  # Master list of all scraped questions
                                                    
                                                    # --- Extract Question 1 ---
                                                    q_html = q_json.get('effects', {}).get('html', '')
                                                    if q_html:
                                                        q_soup = BeautifulSoup(q_html, 'html.parser')
                                                        
                                                        # Find total pages
                                                        page_links = q_soup.find_all(lambda tag: tag.has_attr('wire:click') and 'setCurrentPages' in tag['wire:click'])
                                                        for link in page_links:
                                                            match = re.search(r'setCurrentPages\((\d+)\)', link['wire:click'])
                                                            if match:
                                                                page_num = int(match.group(1))
                                                                if page_num > total_pages:
                                                                    total_pages = page_num
                                                        
                                                        print(f"  [+] Total questions found: {total_pages}")
                                                        
                                                        def extract_question_data(soup, page_number):
                                                            """Helper to extract question data from a Livewire HTML response."""
                                                            q_data = {"number": page_number}
                                                            
                                                            # Metadata
                                                            q_id_el = soup.find('input', {'name': 'q_id'})
                                                            q_data["q_id"] = q_id_el['value'] if q_id_el else ""
                                                            opt_order_el = soup.find('input', {'name': 'option_order'})
                                                            q_data["option_order"] = opt_order_el['value'] if opt_order_el else ""
                                                            q_type_el = soup.find('input', {'name': 'q_type'})
                                                            q_data["q_type"] = q_type_el['value'] if q_type_el else "mcq"
                                                            display_pos_el = soup.find('input', {'name': 'display_pos'})
                                                            q_data["display_pos"] = display_pos_el['value'] if display_pos_el else str(page_number)
                                                            screen_el = soup.find('input', {'name': 'screen'})
                                                            q_data["screen"] = screen_el['value'] if screen_el else str(page_number)
                                                            
                                                            # Question text
                                                            question_div = soup.find('div', class_='question')
                                                            q_data["text"] = question_div.get_text(separator="\n", strip=True) if question_div else f"Question {page_number}"
                                                            
                                                            # Options
                                                            options = soup.find_all('label', class_='checkcontainer')
                                                            q_data["options"] = []       # display texts
                                                            q_data["option_values"] = [] # form values
                                                            for opt in options:
                                                                opt_text = opt.find('div').text.strip() if opt.find('div') else ""
                                                                input_val = opt.find('input').get('value') if opt.find('input') else ""
                                                                q_data["options"].append(opt_text)
                                                                q_data["option_values"].append(input_val)
                                                            
                                                            return q_data
                                                        
                                                        # Collect Q1
                                                        q1_data = extract_question_data(q_soup, 1)
                                                        all_questions.append(q1_data)
                                                        print(f"  [Q1] Collected: {q1_data['text'][:80]}...")
                                                        
                                                        # --- Collect remaining questions (Q2 to QN) ---
                                                        for page in range(2, total_pages + 1):
                                                            # Navigate to next question WITHOUT submitting answers
                                                            nav_payload = {
                                                                "fingerprint": question_component["fingerprint"],
                                                                "serverMemo": current_serverMemo,
                                                                "updates": [
                                                                    {
                                                                        "type": "callMethod",
                                                                        "payload": {
                                                                            "method": "setCurrentPages",
                                                                            "params": [page]
                                                                        }
                                                                    },
                                                                    {
                                                                        "type": "callMethod",
                                                                        "payload": {
                                                                            "method": "loadQuestion",
                                                                            "params": []
                                                                        }
                                                                    }
                                                                ]
                                                            }
                                                            
                                                            p_resp = session.post(q_url, json=nav_payload, headers=q_headers, verify=False)
                                                            p_resp.raise_for_status()
                                                            p_json = p_resp.json()
                                                            
                                                            # Update server memo
                                                            new_memo = p_json.get('serverMemo', {})
                                                            if new_memo:
                                                                current_serverMemo['checksum'] = new_memo.get('checksum', current_serverMemo['checksum'])
                                                                current_serverMemo['htmlHash'] = new_memo.get('htmlHash', current_serverMemo['htmlHash'])
                                                                if 'data' in new_memo:
                                                                    current_serverMemo['data'].update(new_memo['data'])
                                                            
                                                            p_html = p_json.get('effects', {}).get('html', '')
                                                            if p_html:
                                                                p_soup = BeautifulSoup(p_html, 'html.parser')
                                                                qn_data = extract_question_data(p_soup, page)
                                                                all_questions.append(qn_data)
                                                                print(f"  [Q{page}] Collected: {qn_data['text'][:80]}...")
                                                            else:
                                                                print(f"  [Q{page}] WARNING: No HTML returned, skipping.")
                                                        
                                                        print(f"\n  [+] Collection complete: {len(all_questions)}/{total_pages} questions scraped.\n")
                                                        
                                                        # ====================================================
                                                        # PHASE 2: AI ENSEMBLE SOLVING (batch mode)
                                                        # ====================================================
                                                        from ai_solver import solve_all_questions
                                                        solved_questions = solve_all_questions(all_questions)
                                                        
                                                        # ====================================================
                                                        # PHASE 3: SUBMIT ALL ANSWERS
                                                        # ====================================================
                                                        print(f"{'='*70}")
                                                        print(f"  PHASE 3: SUBMITTING ALL ANSWERS")
                                                        print(f"{'='*70}")
                                                        
                                                        # Navigate back to Q1 first
                                                        print("  [*] Navigating back to Question 1...")
                                                        nav_back = {
                                                            "fingerprint": question_component["fingerprint"],
                                                            "serverMemo": current_serverMemo,
                                                            "updates": [
                                                                {
                                                                    "type": "callMethod",
                                                                    "payload": {"method": "setCurrentPages", "params": [1]}
                                                                },
                                                                {
                                                                    "type": "callMethod",
                                                                    "payload": {"method": "loadQuestion", "params": []}
                                                                }
                                                            ]
                                                        }
                                                        back_resp = session.post(q_url, json=nav_back, headers=q_headers, verify=False)
                                                        back_resp.raise_for_status()
                                                        back_json = back_resp.json()
                                                        new_memo = back_json.get('serverMemo', {})
                                                        if new_memo:
                                                            current_serverMemo['checksum'] = new_memo.get('checksum', current_serverMemo['checksum'])
                                                            current_serverMemo['htmlHash'] = new_memo.get('htmlHash', current_serverMemo['htmlHash'])
                                                            if 'data' in new_memo:
                                                                current_serverMemo['data'].update(new_memo['data'])
                                                        
                                                        # Now submit each answer by navigating through questions
                                                        for i, q in enumerate(solved_questions):
                                                            qn = q["number"]
                                                            answer_val = q["ai_answer_value"]
                                                            ai_idx = q["ai_answer_index"] + 1  # 1-indexed for display
                                                            
                                                            # Build the answer data for recordMarks
                                                            mark_data = {
                                                                "screen": q["screen"],
                                                                "currentScreen": q["screen"],
                                                                "answer": answer_val,
                                                                "option_order": q["option_order"],
                                                                "q_id": q["q_id"],
                                                                "display_pos": q["display_pos"],
                                                                "q_type": q["q_type"]
                                                            }
                                                            
                                                            # Navigate to next question while submitting current answer
                                                            next_page = qn + 1 if qn < total_pages else qn
                                                            submit_payload = {
                                                                "fingerprint": question_component["fingerprint"],
                                                                "serverMemo": current_serverMemo,
                                                                "updates": [
                                                                    {
                                                                        "type": "callMethod",
                                                                        "payload": {
                                                                            "method": "recordMarks",
                                                                            "params": [mark_data]
                                                                        }
                                                                    },
                                                                    {
                                                                        "type": "callMethod",
                                                                        "payload": {
                                                                            "method": "setCurrentPages",
                                                                            "params": [next_page]
                                                                        }
                                                                    },
                                                                    {
                                                                        "type": "callMethod",
                                                                        "payload": {
                                                                            "method": "loadQuestion",
                                                                            "params": []
                                                                        }
                                                                    }
                                                                ]
                                                            }
                                                            
                                                            s_resp = session.post(q_url, json=submit_payload, headers=q_headers, verify=False)
                                                            s_resp.raise_for_status()
                                                            s_json = s_resp.json()
                                                            
                                                            # Update server memo
                                                            new_memo = s_json.get('serverMemo', {})
                                                            if new_memo:
                                                                current_serverMemo['checksum'] = new_memo.get('checksum', current_serverMemo['checksum'])
                                                                current_serverMemo['htmlHash'] = new_memo.get('htmlHash', current_serverMemo['htmlHash'])
                                                                if 'data' in new_memo:
                                                                    current_serverMemo['data'].update(new_memo['data'])
                                                            
                                                            opt_text = q["options"][q["ai_answer_index"]] if q["ai_answer_index"] < len(q["options"]) else "?"
                                                            print(f"  [Q{qn}] Submitted Option {ai_idx}: {opt_text[:60]} ✓")
                                                        
                                                        print(f"\n  {'='*60}")
                                                        print(f"  ALL {len(solved_questions)} ANSWERS SUBMITTED SUCCESSFULLY!")
                                                        print(f"  {'='*60}\n")
                                                        
                                                    else:
                                                        print("  [-] Failed to extract HTML from questionbutton response.")
                                                        
                                                except Exception as e:
                                                    import traceback
                                                    print(f"  [-] Failed during exam processing: {e}")
                                                    traceback.print_exc()
                                            else:
                                                print("  [-] Could not find the 'questionbutton' Livewire component on the exam page.")
                                    else:
                                        print(f"  [-] Failed to start exam: {start_json.get('msg', 'Unknown Error')}")
                                        
                                else:
                                    print("  [-] Could not find start exam Javascript payload in the instruction page.")
                                    
                            except Exception as e:
                                print(f"  [-] Error processing active paper: {e}")
                    
        except Exception as e:
            print(f"  [-] Failed to fetch active papers: {e}")

    else:
        print("\n[-] Login processed, but no redirect instruction was returned by the server.")
        
        # Check if the server sent back a specific error message in the HTML
        html_content = response_json.get('effects', {}).get('html', '')
        if html_content:
            err_soup = BeautifulSoup(html_content, 'html.parser')
            error_alert = err_soup.find('div', class_='alert-danger')
            if error_alert:
                clean_err = error_alert.text.replace('×', '').strip()
                print(f"[-] Server says: {clean_err}")
                return
                
        print("[-] Unknown error. Server Response (Raw):")
        print(response_json)

if __name__ == "__main__":
    main()
