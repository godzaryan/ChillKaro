import requests
import json
from bs4 import BeautifulSoup
import urllib3
import urllib.parse
import re
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USERNAME = input("Enter your Username / Roll No: ").strip()
PASSWORD = input("Enter your Password: ").strip()

session = requests.Session()
base_url = "https://makauttest3.ucanapply.com"
get_url = f"{base_url}/onlineexam/public/"
post_url = f"{base_url}/onlineexam/public/livewire/message/login-page"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html, application/xhtml+xml, application/xml",
    "Accept-Language": "en-US,en;q=0.9"
}

def deep_merge(target, source):
    for k, v in source.items():
        if isinstance(v, dict) and k in target and isinstance(target[k], dict):
            deep_merge(target[k], v)
        else:
            target[k] = v

def extract_question_data(soup, page_number):
    q_data = {"number": page_number}
    
    q_id_el = soup.find('input', {'name': 'q_id'})
    opt_order_el = soup.find('input', {'name': 'option_order'})
    q_type_el = soup.find('input', {'name': 'q_type'})
    display_pos_el = soup.find('input', {'name': 'display_pos'})
    screen_el = soup.find('input', {'name': 'screen'})
    
    q_data['q_id'] = q_id_el['value'] if q_id_el else ""
    q_data['option_order'] = opt_order_el['value'] if opt_order_el else ""
    q_data['q_type'] = q_type_el['value'] if q_type_el else "mcq"
    q_data['display_pos'] = display_pos_el['value'] if display_pos_el else str(page_number)
    q_data['screen'] = screen_el['value'] if screen_el else str(page_number)
    
    q_div = soup.find('div', class_='question')
    q_data['text'] = q_div.get_text(separator='\n', strip=True) if q_div else f"Question {page_number}"
    
    opts = []
    for lbl in soup.find_all('label', class_='checkcontainer'):
        opt_text = lbl.find('div').get_text(strip=True) if lbl.find('div') else lbl.get_text(strip=True)
        opts.append(opt_text)
    q_data['options'] = opts
    
    return q_data

def main():
    print("\n[*] Logging in...")
    resp = session.get(get_url, headers=headers, verify=False)
    soup = BeautifulSoup(resp.text, 'html.parser')
    csrf_token = soup.find('meta', {'name': 'csrf-token'})['content']
    lw_data = json.loads(soup.find('div', class_='login-form1')['wire:initial-data'])
    
    payload = {
        "fingerprint": lw_data["fingerprint"],
        "serverMemo": lw_data["serverMemo"],
        "updates": [
            {"type": "syncInput", "payload": {"name": "password", "value": PASSWORD}},
            {"type": "syncInput", "payload": {"name": "username", "value": USERNAME}},
            {"type": "callMethod", "payload": {"method": "submit", "params": []}}
        ]
    }
    
    post_headers = headers.copy()
    post_headers.update({
        "Content-Type": "application/json", "X-Livewire": "true", "X-CSRF-TOKEN": csrf_token,
        "Origin": base_url, "Referer": get_url
    })
    
    post_resp = session.post(post_url, json=payload, headers=post_headers, verify=False)
    resp_json = post_resp.json()
    
    if resp_json.get('serverMemo', {}).get('data', {}).get('alreadySession') == 'Y':
        new_memo = resp_json.get('serverMemo', {})
        payload['serverMemo']['htmlHash'] = new_memo.get('htmlHash', payload['serverMemo']['htmlHash'])
        payload['serverMemo']['checksum'] = new_memo.get('checksum', payload['serverMemo']['checksum'])
        for k, v in new_memo.get('data', {}).items():
            payload['serverMemo']['data'][k] = v
        payload['updates'] = [
            {"type": "callMethod", "payload": {"method": "$set", "params": ["destroy", "Y"]}},
            {"type": "callMethod", "payload": {"method": "submit", "params": []}}
        ]
        post_resp = session.post(post_url, json=payload, headers=post_headers, verify=False)
        resp_json = post_resp.json()
        
    dashboard_url = resp_json.get('effects', {}).get('redirect')
    if not dashboard_url:
        print("[!] Login failed. Check credentials.")
        sys.exit(1)
        
    session.get(dashboard_url, headers=headers, verify=False)
    
    active_headers = headers.copy()
    active_headers.update({
        "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": urllib.parse.unquote(session.cookies.get('XSRF-TOKEN', ''))
    })
    
    print("[*] Scanning for active exams...")
    active_resp = session.get(f"{base_url}/onlineexam/public/student/getActivePapper", headers=active_headers, verify=False)
    active_soup = BeautifulSoup(active_resp.json()['html'], 'html.parser')
    paper_link = active_soup.find('a', class_='list-group-item')
    if not paper_link:
        print("[!] No active exams found right now.")
        sys.exit(1)
        
    paper_url = paper_link.get('href')
    
    instr_resp = session.get(paper_url, headers=headers, verify=False)
    paperID = re.search(r'paperID:\s*(\d+)', instr_resp.text).group(1)
    paper_type = re.search(r'paper_type:\s*(\d+)', instr_resp.text).group(1)
    start_date = re.search(r'start_date:\s*(\d+)', instr_resp.text).group(1)
    crypt_name = re.search(r'crypt_name:\s*["\']([^"\']+)["\']', instr_resp.text).group(1)
    
    print("[*] Opening Exam Interface...")
    start_resp = session.post(f"{base_url}/onlineexam/public/student/check-exam-started-invigilator", json={
        "paperID": int(paperID), "paper_type": int(paper_type), "start_date": int(start_date), "crypt_name": crypt_name
    }, headers=active_headers, verify=False)
    
    start_json = start_resp.json()
    if not start_json.get('status'):
        print(f"[!] Exam check failed: {start_json.get('msg', 'Unknown error')}")
        sys.exit(1)
        
    exam_url = start_json.get('url')
    
    exam_resp = session.get(exam_url, headers=headers, verify=False)
    exam_soup = BeautifulSoup(exam_resp.text, 'html.parser')
    exam_csrf = exam_soup.find('meta', {'name': 'csrf-token'})['content']
    
    q_comp = None
    for el in exam_soup.find_all(attrs={"wire:initial-data": True}):
        d = json.loads(el['wire:initial-data'])
        if d.get('fingerprint', {}).get('name') == 'questionbutton':
            q_comp = d
            break
            
    q_url = f"{base_url}/onlineexam/public/livewire/message/questionbutton"
    q_headers = headers.copy()
    q_headers.update({
        "Content-Type": "application/json", "X-Livewire": "true", "X-CSRF-TOKEN": exam_csrf,
        "Origin": base_url, "Referer": exam_url
    })
    
    print("\n============================================================")
    print("  EXTRACTING EXAM QUESTIONS")
    print("============================================================")
    
    # FETCH Q1
    q1_resp = session.post(q_url, json={
        "fingerprint": q_comp["fingerprint"], "serverMemo": q_comp["serverMemo"],
        "updates": [{"type": "callMethod", "payload": {"method": "loadQuestion", "params": []}}]
    }, headers=q_headers, verify=False)
    q1_json = q1_resp.json()
    
    current_serverMemo = q_comp["serverMemo"].copy()
    current_serverMemo['data'] = q_comp["serverMemo"].get("data", {}).copy()
    new_memo1 = q1_json.get('serverMemo', {})
    if new_memo1:
        deep_merge(current_serverMemo, new_memo1)
        
    q1_html = q1_json.get('effects', {}).get('html', '')
    soup1 = BeautifulSoup(q1_html, 'html.parser')
    
    total_pages = 1
    for link in soup1.find_all(lambda tag: tag.has_attr('wire:click') and 'setCurrentPages' in tag['wire:click']):
        match = re.search(r'setCurrentPages\((\d+)\)', link['wire:click'])
        if match: total_pages = max(total_pages, int(match.group(1)))
        
    q1_data = extract_question_data(soup1, 1)
    
    def print_q(q):
        print(f"\n[Q{q['number']}] {q['text']}")
        for i, opt in enumerate(q['options']):
            print(f"   {i+1}) {opt}")
            
    print_q(q1_data)
    
    current_q_data = q1_data
    
    # Fetch remaining questions
    for page in range(2, total_pages + 1):
        mark_data = {
            "screen": current_q_data["screen"],
            "currentScreen": current_q_data["screen"],
            "answer": "",
            "option_order": current_q_data["option_order"],
            "q_id": current_q_data["q_id"],
            "display_pos": current_q_data["display_pos"],
            "q_type": current_q_data["q_type"]
        }
        
        nav_payload = {
            "fingerprint": q_comp["fingerprint"],
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
                        "method": "recordMarks",
                        "params": [mark_data]
                    }
                }
            ]
        }
        
        p_resp = session.post(q_url, json=nav_payload, headers=q_headers, verify=False)
        p_json = p_resp.json()
        
        new_memo = p_json.get('serverMemo', {})
        if new_memo:
            deep_merge(current_serverMemo, new_memo)
            
        p_html = p_json.get('effects', {}).get('html', '')
        if p_html:
            p_soup = BeautifulSoup(p_html, 'html.parser')
            qn_data = extract_question_data(p_soup, page)
            print_q(qn_data)
            current_q_data = qn_data

    print("\n============================================================")
    print("  EXTRACTION COMPLETE!")
    print("============================================================")

if __name__ == "__main__":
    main()
