import base64
import hashlib
import json
import re

import requests
import streamlit as st


st.set_page_config(page_title="Variant Tool (DE)", layout="wide")

st.markdown(
    """
<style>
div.stButton > button[kind="primary"]{
  background:#ef4444 !important;
  border:1px solid #ef4444 !important;
  color:#ffffff !important;
  font-weight:700 !important;
}
div.stButton > button[kind="primary"]:hover{
  background:#dc2626 !important;
  border-color:#dc2626 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


def safe_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


OPENROUTER_API_KEY = safe_secret("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Models wie im bisherigen Tool
OPENROUTER_MODEL_VISION = safe_secret("OPENROUTER_MODEL_VISION", "google/gemini-3-flash-preview").strip()

TEMPERATURE = 0
TIMEOUT_SEC = 90

SYSTEM_PROMPT = """
I will upload a product title and a supplier variant screenshot.

Task:
Determine the correct eBay.de variant attribute and the correct German variant options.

Rules:
- Output only one final result
- No explanations
- No alternatives
- Keep the visible option order exactly as shown in the screenshot
- For each option, output:
  visible English option = correct German option
- Do not blindly trust the supplier variant key
- Choose the real customer-facing attribute in German
- Use clear German customer-friendly names
- If the supplier key is misleading, correct it
- Do not include supplier codes unless absolutely necessary

Format:

Attribut:
[attribute in German]

Optionen:
- [visible option 1] = [German option 1]
- [visible option 2] = [German option 2]
- [visible option 3] = [German option 3]
""".strip()


def clear_all():
    keys_to_clear = [
        "product_title",
        "out_attribute",
        "out_options",
        "out_options_rows",
        "image_hash",
    ]
    for key in keys_to_clear:
        st.session_state[key] = [] if key == "out_options_rows" else ""

    current_uploader_key = st.session_state.get("uploader_key", 0)
    st.session_state.pop(f"variant_image_{current_uploader_key}", None)
    st.session_state["uploader_key"] = current_uploader_key + 1


def call_openrouter(messages: list[dict]) -> str:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("Missing OPENROUTER_API_KEY in Streamlit secrets.")

    payload = {
        "model": OPENROUTER_MODEL_VISION,
        "messages": messages,
        "temperature": TEMPERATURE,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://example.com",
        "X-Title": "Variant Tool (DE)",
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=TIMEOUT_SEC)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def clean_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_variant_output(text: str) -> dict:
    raw = clean_text(text)

    attr_match = re.search(r"(?im)^\s*Attribut:\s*(.+?)\s*$", raw)
    options_block = re.search(r"(?is)Optionen:\s*(.+)$", raw)

    options = []
    if options_block:
        for line in options_block.group(1).splitlines():
            line = re.sub(r"^\s*[-*•]\s*", "", line).strip()
            if line:
                options.append(line)

    return {
        "raw": raw,
        "attribute": attr_match.group(1).strip() if attr_match else "",
        "options": options,
    }


def render_copy_button(label: str, text: str, key: str):
    button_id = f"copy-btn-{key}"
    payload = json.dumps(text or "")
    button_label = json.dumps(label)
    html_content = f"""
        <div style=\"display: inline-block; margin-right: 8px;\">
          <button id=\"{button_id}\" style=\"padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;background:#f8fafc;cursor:pointer;font-size:0.9rem;\">
            {label}
          </button>
          <script>
            (() => {{
              const btn = document.getElementById('{button_id}');
              if (!btn) return;
              const original = {button_label};
              const text = {payload};
              const copy = async () => {{
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                  return navigator.clipboard.writeText(text);
                }}
                const el = document.createElement('textarea');
                el.value = text;
                el.setAttribute('readonly', '');
                el.style.position = 'fixed';
                el.style.opacity = '0';
                document.body.appendChild(el);
                el.select();
                document.execCommand('copy');
                document.body.removeChild(el);
              }};
              btn.addEventListener('click', async () => {{
                btn.disabled = true;
                let ok = true;
                try {{
                  await copy();
                }} catch (err) {{
                  ok = false;
                  console.error(err);
                }}
                btn.innerText = ok ? '✓' : '⚠';
                setTimeout(() => {{
                  btn.innerText = original;
                  btn.disabled = false;
                }}, 1000);
              }});
            }})();
          </script>
        </div>
        """
    st.components.v1.html(html_content, height=42)


st.title("Variant Tool (DE)")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input")

    st.button("Clear", use_container_width=True, on_click=clear_all)

    st.text_area(
        "Product title",
        height=130,
        key="product_title",
        placeholder="Paste product title here...",
    )

    uploader_key = st.session_state.get("uploader_key", 0)
    uploaded_image = st.file_uploader(
        "Variant screenshot upload (jpg/png/webp)",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"variant_image_{uploader_key}",
        accept_multiple_files=False,
    )

    st.caption("Upload the supplier variant screenshot.")

    if uploaded_image and hasattr(uploaded_image, "getvalue"):
        image_bytes = uploaded_image.getvalue()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        st.session_state["image_hash"] = image_hash
        st.image(uploaded_image, caption="Uploaded screenshot", use_container_width=True)

    btn_generate = st.button("Generate", type="primary", use_container_width=True)

    if btn_generate:
        product_title = st.session_state.get("product_title", "").strip()

        if not product_title:
            st.warning("Please paste the product title first.")
        elif not uploaded_image or not hasattr(uploaded_image, "getvalue"):
            st.warning("Please upload a screenshot first.")
        else:
            if not OPENROUTER_API_KEY:
                st.warning("Missing OPENROUTER_API_KEY in Streamlit secrets.")
            else:
                image_bytes = uploaded_image.getvalue()
                data_url = f"data:{uploaded_image.type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Product title:\n{product_title}",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    },
                ]

                with st.spinner("Generating variant names..."):
                    raw_output = call_openrouter(messages)
                    parsed = parse_variant_output(raw_output)

                options_rows = []
                for option_line in parsed["options"]:
                    if "=" in option_line:
                        left_part, right_part = option_line.split("=", 1)
                        options_rows.append({"control": left_part.strip(), "ebay": right_part.strip()})
                    else:
                        clean_line = option_line.strip()
                        options_rows.append({"control": clean_line, "ebay": clean_line})

                st.session_state["out_attribute"] = parsed["attribute"]
                st.session_state["out_options"] = "\n".join(f"- {opt}" for opt in parsed["options"])
                st.session_state["out_options_rows"] = options_rows
                st.rerun()

with col2:
    st.subheader("Output")

    st.text_input("Attribut", key="out_attribute")

    option_rows = st.session_state.get("out_options_rows", [])
    if option_rows:
        for idx, option_row in enumerate(option_rows):
            control_col, ebay_col = st.columns([2, 3], gap="large")
            with control_col:
                st.caption("Nur Kontrolle")
                st.caption(option_row.get("control", ""))
            with ebay_col:
                st.caption("Für eBay kopieren")
                st.markdown(f"**{option_row.get('ebay', '')}**")

            if idx < len(option_rows) - 1:
                st.divider()
    elif st.session_state.get("out_options"):
        st.info("Keine strukturierten Optionen gefunden. Bitte Debug/Raw prüfen.")

    with st.expander("Debug/Raw Optionen", expanded=False):
        st.text_area("Optionen (raw)", height=220, key="out_options")

    combined_output = ""
    if st.session_state.get("out_attribute") or st.session_state.get("out_options"):
        combined_output = (
            f"Attribut:\n{st.session_state.get('out_attribute', '')}\n\n"
            f"Optionen:\n{st.session_state.get('out_options', '')}"
        )

    col_copy1, col_copy2 = st.columns(2)
    with col_copy1:
        render_copy_button("Copy Attribute", st.session_state.get("out_attribute", ""), "copy_attr")
    with col_copy2:
        render_copy_button("Copy Full Output", combined_output, "copy_full")
