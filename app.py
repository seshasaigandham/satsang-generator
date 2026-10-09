import os
import re
import random
import base64
import tempfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from playwright.sync_api import sync_playwright

app = Flask(__name__)

PAGE_1_ROWS = [
    {"type": "Starting Prayer:", "start": "", "end": "", "row_class": "bg-yellow", "type_colspan": 1, "dev_colspan": 3},
    {"type": "Pledge:", "start": "", "end": "", "row_class": "bg-yellow", "type_colspan": 1, "dev_colspan": 3},
    {"type": "Poorvangam", "start": "1", "end": "9", "devotee": "VISVAS", "row_class": "bg-pink"},
    {"type": "Poorvangam", "start": "10", "end": "16", "row_class": "bg-pink"},
    {"type": "Poorvangam", "start": "17", "end": "22", "row_class": "bg-pink"},
    {"type": "Nyasa", "start": "", "end": "", "row_class": "bg-pink", "type_colspan": 3, "dev_colspan": 1},
    {"type": "Dhyaanam", "start": "1", "end": "4", "row_class": "bg-blue"},
    {"type": "Dhyaanam", "start": "5", "end": "8", "row_class": "bg-blue"},
    {"type": "Shlokam", "start": "1", "end": "9", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "10", "end": "19", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "20", "end": "29", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "30", "end": "39", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "40", "end": "49", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "50", "end": "58", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "59", "end": "68", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "69", "end": "78", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "79", "end": "88", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "89", "end": "98", "row_class": "bg-yellow"},
    {"type": "Shlokam", "start": "99", "end": "108", "row_class": "bg-yellow"},
    {"type": "Phalashruti", "start": "1", "end": "6", "row_class": "bg-green"},
    {"type": "Phalashruti", "start": "7", "end": "13", "row_class": "bg-green"},
]

PAGE_2_ROWS = [
    {"type": "Phalashruti", "start": "14", "end": "19", "row_class": "bg-green"},
    {"type": "Phalashruti", "start": "20", "end": "26", "row_class": "bg-green"},
    {"type": "Phalashruti", "start": "27", "end": "33", "row_class": "bg-green"},
    {"type": "Kshama Prarthana", "start": "", "end": "", "row_class": "bg-lightpink", "type_colspan": 3, "dev_colspan": 1},
    {"type": "Ending Prayer:", "start": "", "end": "", "row_class": "bg-lightpink", "type_colspan": 1, "dev_colspan": 3},
]

PAGE_1_BACKUPS = [
    {"start_idx": 0, "rows": 2, "bg": "bg-backup-orange"},
    {"start_idx": 2, "rows": 4, "bg": "bg-backup-green"},
    {"start_idx": 6, "rows": 2, "bg": "bg-backup-green"},
    {"start_idx": 8, "rows": 4, "bg": "bg-backup-orange"},
    {"start_idx": 12, "rows": 3, "bg": "bg-backup-green"},
    {"start_idx": 15, "rows": 2, "bg": "bg-backup-red"},
    {"start_idx": 17, "rows": 2, "bg": "bg-backup-orange"},
    {"start_idx": 19, "rows": 2, "bg": "bg-backup-pink"},
]

PAGE_2_BACKUPS = [
    {"start_idx": 0, "rows": 3, "bg": "bg-backup-gray"},
    {"start_idx": 3, "rows": 2, "bg": "bg-backup-cyan"},
]

def clean_invisible_chars(text):
    bad_chars = ['\u200b', '\u200c', '\u200d', '\u200e', '\u200f', '\u2060', '\ufeff', '\xa0']
    for ch in bad_chars:
        text = text.replace(ch, ' ')
    return re.sub(r' +', ' ', text)

def format_camel_case(name_str):
    parts = re.split(r'(\s+|\.)', name_str)
    result = []
    for part in parts:
        if part.strip() and part != '.':
            result.append(part.capitalize())
        else:
            result.append(part)
    return "".join(result).strip()

def format_ordinal_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%d-%m-%Y")
        day = dt.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{day}{suffix} {dt.strftime('%B, %Y')}"
    except Exception:
        return date_str

def parse_signup_message(text):
    cleaned = clean_invisible_chars(text)
    lines = [l.strip() for l in cleaned.split("\n") if l.strip()]
    
    satsang_num = "130"
    batch_num = "A1195"
    datetime_str = "10-10-2026 8 AM IST"
    date_only = "10-10-2026"

    for line in lines:
        m_sat = re.search(r'Weekly Satsang\s*[-–]?\s*(\d+)', line, re.IGNORECASE)
        if m_sat:
            satsang_num = m_sat.group(1)
        m_batch = re.search(r'\b(A\d+)\b', line, re.IGNORECASE)
        if m_batch:
            batch_num = m_batch.group(1)
        
        d_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', line)
        if d_match:
            date_only = d_match.group(1).replace("/", "-")
            t_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)(?:\s*IST)?)', line)
            time_part = t_match.group(1).strip() if t_match else "8 AM IST"
            if "IST" not in time_part:
                time_part += " IST"
            datetime_str = f"{date_only} {time_part}"

    devotees, backups = [], []
    ignore_phrases = ["participants willing", "please give", "please add", "forwarded", "weekly satsang"]

    for line in lines:
        lower_line = line.lower()
        if any(ign in lower_line for ign in ignore_phrases):
            continue

        nm = re.match(r'^\s*(\d+)[\.\)\:\-]\s*(.+)', line)
        if nm:
            name_raw = nm.group(2).strip()
            is_backup = bool(re.search(r'\(?\s*back[\s\-]?up\s*\)?', name_raw, re.IGNORECASE))
            clean_name = re.sub(r'\(?\s*back[\s\-]?up\s*\)?', '', name_raw, flags=re.IGNORECASE).strip()
            clean_name = clean_name.strip(" -.,")
            clean_name = format_camel_case(clean_name)
            
            if clean_name and len(clean_name) > 1 and not any(ign in clean_name.lower() for ign in ["message", "satsang"]):
                devotees.append(clean_name)
                if is_backup:
                    backups.append(clean_name)

    if not backups:
        backups = devotees[:]

    header_info = {
        "title": f"WEEKLY SATSANG - {satsang_num} {datetime_str}",
        "batch": batch_num,
        "datetime": datetime_str,
        "date_only": date_only,
        "satsang_num": satsang_num
    }
    return header_info, devotees, backups

def generate_caption(header_info):
    formatted_date = format_ordinal_date(header_info["date_only"])
    time_part = header_info['datetime'].split(" ", 1)[1] if " " in header_info['datetime'] else "8 AM IST"
    return (
        f"WEEKLY SATSANG -{header_info['satsang_num']} on {header_info['datetime']}\n"
        f"Om Namo Narayanaya 🙏\n"
        f"I request all devotees to please go through the Allocated Shlokas List for upcoming Weekly Satsang on {formatted_date} {time_part}"
    )

def build_pdf_html(header_info, devotees, backups):
    img_tag = ""
    for loc in ["vishwaroopam.jpg", "vishwaroopam.jpeg", "vishwaroopam.png", "image.jpg"]:
        if os.path.exists(loc):
            with open(loc, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
                mime = "image/png" if loc.endswith(".png") else "image/jpeg"
                img_tag = f'<img src="data:{mime};base64,{img_b64}" class="banner"/>'
            break

    pool = devotees[:]
    random.shuffle(pool)
    d_idx = 0

    def assign_list(row_list):
        nonlocal d_idx
        assigned = []
        for r in row_list:
            entry = dict(r)
            if "devotee" not in entry:
                entry["devotee"] = pool[d_idx % len(pool)]
                d_idx += 1
            assigned.append(entry)
        return assigned

    p1_assigned = assign_list(PAGE_1_ROWS)
    p2_assigned = assign_list(PAGE_2_ROWS)

    def map_backups_no_overlap(rules, assigned_rows):
        cell_map = {}
        usage_count = {name: 0 for name in backups}

        for rule in rules:
            start_i = rule["start_idx"]
            span_len = rule["rows"]

            chanters_in_block = {r.get("devotee", "") for r in assigned_rows[start_i : start_i + span_len]}
            candidates = [b for b in backups if b not in chanters_in_block]
            if not candidates:
                candidates = [d for d in devotees if d not in chanters_in_block]
            if not candidates:
                candidates = backups[:]

            random.shuffle(candidates)
            chosen_backup = min(candidates, key=lambda n: usage_count.get(n, 0))
            usage_count[chosen_backup] = usage_count.get(chosen_backup, 0) + 1

            cell_map[start_i] = {
                "rows": span_len,
                "name": chosen_backup,
                "bg": rule["bg"]
            }
        return cell_map

    p1_backups = map_backups_no_overlap(PAGE_1_BACKUPS, p1_assigned)
    p2_backups = map_backups_no_overlap(PAGE_2_BACKUPS, p2_assigned)

    def render_table_rows(assigned_rows, backup_map):
        html_rows = ""
        for i, row in enumerate(assigned_rows):
            r_class = row["row_class"]
            r_type = row["type"]
            r_dev = row["devotee"]
            r_start = row["start"]
            r_end = row["end"]

            html_rows += f'<tr class="{r_class}">'
            if row.get("type_colspan", 1) > 1:
                html_rows += f'<td colspan="{row["type_colspan"]}">{r_type}</td><td>{r_dev}</td>'
            elif row.get("dev_colspan", 1) > 1:
                html_rows += f'<td>{r_type}</td><td colspan="{row["dev_colspan"]}">{r_dev}</td>'
            else:
                html_rows += f'<td>{r_type}</td><td class="center">{r_start}</td><td class="center">{r_end}</td><td>{r_dev}</td>'

            if i in backup_map:
                b = backup_map[i]
                html_rows += f'<td rowspan="{b["rows"]}" class="{b["bg"]} backup-cell">{b["name"]}</td>'
            html_rows += '</tr>'
        return html_rows

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      @page {{
        size: A4 portrait;
        margin: 6mm 8mm 6mm 8mm;
      }}
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        margin: 0;
        padding: 0;
        color: #000;
      }}
      .page-break {{ page-break-before: always; }}
      .banner {{ width: 100%; max-height: 200px; object-fit: cover; display: block; margin-bottom: 4px; }}
      table {{ width: 100%; border-collapse: collapse; font-size: 13px; font-weight: 600; }}
      th, td {{ border: 1.5px solid #222; padding: 3.5px 6px; }}
      .center {{ text-align: center; }}
      .header-bg {{ background-color: #b9cbe6; }}
      .title-cell {{ background-color: #b9cbe6; text-align: center; font-size: 15px; font-weight: 800; padding: 4px; }}
      .bg-yellow {{ background-color: #fffb60; }}
      .bg-pink {{ background-color: #f7cbd1; }}
      .bg-blue {{ background-color: #9cd4e6; }}
      .bg-green {{ background-color: #bee6be; }}
      .bg-lightpink {{ background-color: #f7cbd1; }}
      .backup-cell {{ text-align: center; vertical-align: middle; }}
      .bg-backup-orange {{ background-color: #f6b26b; }}
      .bg-backup-green {{ background-color: #93c47d; }}
      .bg-backup-red {{ background-color: #e06666; }}
      .bg-backup-pink {{ background-color: #ea9999; }}
      .bg-backup-gray {{ background-color: #999999; }}
      .bg-backup-cyan {{ background-color: #00ffff; }}
    </style>
    </head>
    <body>
      {img_tag}
      <table>
        <tr><td colspan="5" class="title-cell">{header_info['title']}</td></tr>
        <tr class="header-bg">
          <td style="width: 25%;">Batch Number</td>
          <td style="width: 15%;">{header_info['batch']}</td>
          <td colspan="2" style="width: 35%;">Date Time</td>
          <td style="width: 25%;">{header_info['datetime']}</td>
        </tr>
        <tr class="header-bg">
          <td>Shlokam</td>
          <td class="center" style="width: 45px;">Start</td>
          <td class="center" style="width: 45px;">End</td>
          <td>Devotee Name</td>
          <td class="center">Backup Chanter</td>
        </tr>
        {render_table_rows(p1_assigned, p1_backups)}
      </table>

      <div class="page-break"></div>
      <table>
        <tr class="header-bg">
          <td>Shlokam</td>
          <td class="center" style="width: 45px;">Start</td>
          <td class="center" style="width: 45px;">End</td>
          <td>Devotee Name</td>
          <td class="center">Backup Chanter</td>
        </tr>
        {render_table_rows(p2_assigned, p2_backups)}
      </table>
    </body>
    </html>
    """
    return html_content

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Satsang PDF Generator</title>
  <style>
    body { font-family: -apple-system, system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f3f4f6; margin: 0; padding: 20px; display: flex; justify-content: center; }
    .card { background: white; max-width: 650px; width: 100%; padding: 24px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }
    h2 { margin-top: 0; color: #111827; font-size: 20px; }
    p { color: #4b5563; font-size: 14px; }
    textarea { width: 100%; height: 240px; font-family: monospace; font-size: 13px; padding: 12px; border: 1.5px solid #d1d5db; border-radius: 8px; box-sizing: border-box; resize: vertical; }
    button { background: #2563eb; color: white; border: none; font-size: 16px; font-weight: 600; padding: 12px 20px; border-radius: 8px; cursor: pointer; margin-top: 12px; width: 100%; transition: background 0.2s; }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #9ca3af; cursor: not-allowed; }
    .status { margin-top: 15px; padding: 14px; border-radius: 8px; font-size: 14px; display: none; }
    .success { background: #def7ec; color: #03543f; border: 1px solid #bcf0da; }
    .error { background: #fde8e8; color: #9b1c1c; border: 1px solid #f8b4b4; }
    .caption-box { margin-top: 10px; background: white; border: 1px dashed #057a55; padding: 10px; border-radius: 6px; white-space: pre-wrap; font-size: 13px; color: #111827; }
    .copy-btn { background: #057a55; padding: 8px 14px; font-size: 13px; margin-top: 8px; width: auto; }
    .copy-btn:hover { background: #046c4e; }
  </style>
</head>
<body>
  <div class="card">
    <h2>Satsang Allocation & PDF Generator</h2>
    <p>Paste the WhatsApp signup message below and click generate:</p>
    <textarea id="msgBox" placeholder="Paste WhatsApp list here..."></textarea>
    <button id="genBtn" onclick="generatePdf()">📄 Generate & Download PDF</button>
    <div id="statusBox" class="status"></div>
  </div>

  <script>
    let currentCaption = "";

    async function generatePdf() {
      const btn = document.getElementById('genBtn');
      const box = document.getElementById('statusBox');
      const text = document.getElementById('msgBox').value.trim();

      if (!text) {
        alert("Please paste the WhatsApp signup message first!");
        return;
      }

      btn.disabled = true;
      btn.innerText = "Generating PDF (takes ~4s)...";
      box.style.display = "none";

      try {
        const res = await fetch('/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();

        if (data.status === 'ok') {
          currentCaption = data.caption;
          box.className = "status success";
          box.innerHTML = `
            <b>✅ PDF Generated Successfully!</b><br>
            • Devotees: ${data.devotees.join(', ')}<br>
            • Backups: ${data.backups.join(', ')}<br><br>
            <a href="/download/${data.pdf_token}" target="_blank" style="color:#03543f;font-weight:bold;font-size:15px;text-decoration:underline;">📥 Click here to Download PDF</a>
            <hr style="border:0;border-top:1px solid #bcf0da;margin:12px 0;">
            <b>WhatsApp Message Caption:</b>
            <div class="caption-box">${escapeHtml(data.caption)}</div>
            <button class="copy-btn" onclick="copyCaption()">📋 Copy WhatsApp Message</button>
          `;
          box.style.display = "block";
          window.location.href = `/download/${data.pdf_token}`;
        } else {
          box.className = "status error";
          box.innerText = data.error;
          box.style.display = "block";
        }
      } catch (err) {
        box.className = "status error";
        box.innerText = "Error: " + err.message;
        box.style.display = "block";
      } finally {
        btn.disabled = false;
        btn.innerText = "📄 Generate & Download PDF";
      }
    }

    function copyCaption() {
      navigator.clipboard.writeText(currentCaption);
      alert("WhatsApp companion caption copied to clipboard!");
    }

    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
  </script>
</body>
</html>
"""

pdf_store = {}

@app.route('/')
def home():
    return HTML_PAGE

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json() or {}
    raw_text = data.get('message', '').strip()

    header_info, devotees, backups = parse_signup_message(raw_text)
    if not devotees:
        return jsonify({'status': 'error', 'error': 'Could not parse devotee names from text.'}), 400

    html_content = build_pdf_html(header_info, devotees, backups)
    caption = generate_caption(header_info)

    token = f"{random.randint(100000, 999999)}.pdf"
    temp_pdf = os.path.join(tempfile.gettempdir(), token)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html_content, wait_until="networkidle")
        page.pdf(
            path=temp_pdf,
            format="A4",
            print_background=True,
            margin={"top": "6mm", "bottom": "6mm", "left": "8mm", "right": "8mm"}
        )
        browser.close()

    d_parts = header_info["date_only"].split("-")
    download_name = f"VSN_Allocations_{d_parts[0]}_{d_parts[1]}.pdf" if len(d_parts) >= 2 else "VSN_Allocations.pdf"
    pdf_store[token] = (temp_pdf, download_name)

    return jsonify({
        'status': 'ok',
        'pdf_token': token,
        'devotees': devotees,
        'backups': backups,
        'caption': caption
    })

@app.route('/download/<token>')
def download(token):
    if token in pdf_store:
        path, download_name = pdf_store[token]
        return send_file(path, as_attachment=True, download_name=download_name)
    return "File expired or not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
