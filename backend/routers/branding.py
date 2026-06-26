import os
import json
import logging
import requests
import re
from fastapi import APIRouter, HTTPException, Body, Depends, Header, Response, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from firebase_admin import firestore
from google.cloud import bigquery
from ca_client import ConversationalAnalyticsClient
from auth import get_current_user, get_analytics_client
from models import *
from google.api_core import exceptions as google_exceptions

from bq_client import get_live_table_preview
from config import logger, get_project_id, DELETED_CONVOS_FILE, get_deleted_conversations, add_deleted_conversation, BRANDING_FILE
import time

router = APIRouter()


@router.post("/api/branding/generate")
def generate_branding(req: GenerateBrandingRequest, user: dict = Depends(get_current_user)):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    import re

    system_instruction = (
        "You are a branding assistant. Generate a beautiful, professional, and matching dark-mode "
        "visual theme configuration for a company data portal based on the user's prompt and any uploaded logo icon. "
        "If a logo icon is uploaded (as a base64 image or SVG text): "
        "1. Identify its style and brand colors. "
        "2. If it is an SVG logo, analyze the SVG structure and modify/change the color values inside the SVG path/shape elements to match the new brand color theme (e.g., use the generated primary/secondary brand colors, or 'currentColor' for paths). Return this modified SVG as the 'logoSvg' field. "
        "3. If it is a raster image, suggest brand colors that beautifully match the logo's theme, and generate a clean, modern, minimalist SVG vector representation of the logo/concept and return it in 'logoSvg'. "
        "4. Generate a warm, customized data analytics greetings message (welcomeMessage) based on the brand/company name. "
        "\nReturn the result ONLY as a raw JSON object containing these exact fields:\n"
        "- name: The clear display name of the company\n"
        "- primaryColor: A beautiful HSL color matching the company's brand identity, formatted as 'H, S%, L%'\n"
        "- secondaryColor: A matching secondary/accent HSL color, formatted as 'H, S%, L%'\n"
        "- backgroundColorStart: A dark-theme background gradient start color hex code (e.g. #0a0b12)\n"
        "- backgroundColorEnd: A dark-theme background gradient end color hex code (e.g. #121522)\n"
        "- logoText: Logo text in upper case (e.g. COCA-COLA)\n"
        "- welcomeMessage: A warm, customized data analytics greetings message (e.g. Welcome to Coca-Cola Analytics. Ask me about sales volume...)\n"
        "- logoSvg: The SVG code representing the logo. If the user uploaded an SVG, this must be the modified/changed-color SVG. Otherwise, it should be a generated vector logo matching the brand concept, styled with fill/stroke to match the primary/secondary colors."
    )

    try:
        if req.logo_url and not req.logo_image:
            if not is_safe_url(req.logo_url):
                logger.warning(f"SSRF Prevention: Blocked unsafe logo URL download request: {req.logo_url}")
            else:
                try:
                    import requests
                    import base64
                    img_resp = requests.get(req.logo_url, timeout=5)
                    if img_resp.status_code == 200:
                        req.logo_image = base64.b64encode(img_resp.content).decode("utf-8")
                        content_type = img_resp.headers.get("Content-Type")
                        if content_type:
                            req.logo_mime_type = content_type.split(";")[0]
                except Exception as ex:
                    logger.warning(f"Failed to fetch logo from URL {req.logo_url} for theme generation: {ex}")


        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/gemini-1.5-flash:generateContent"
        
        prompt_text = f"Generate a theme configuration for: {req.prompt}"
        if req.logo_svg_content:
            prompt_text += f"\n\nHere is the XML content of the logo SVG uploaded by the user. Modify its color attributes (such as fill, stroke, class, or styles) to match the new color palette, or use 'currentColor' for paths so it integrates cleanly:\n{req.logo_svg_content}"
        
        parts = [{"text": prompt_text}]
        
        if req.logo_image and not req.logo_svg_content:
            base64_data = req.logo_image
            if "," in base64_data:
                base64_data = base64_data.split(",")[1]
            parts.append({
                "inlineData": {
                    "mimeType": req.logo_mime_type or "image/png",
                    "data": base64_data
                }
            })
            
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if candidates:
                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_content:
                    parsed = json.loads(text_content.strip())
                    logger.info(f"Successfully generated branding with Gemini: {parsed['name']}")
                    return parsed

        logger.warning(f"Vertex AI API returned status {resp.status_code}. Falling back to rules-based generator.")
        raise Exception(f"API status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error calling Vertex AI API: {e}. Executing rules-based fallback generator.")
        
        clean_prompt = req.prompt.lower()
        
        # Extract brand name
        brand_name = req.prompt
        for prefix in ["create a theme for", "branding for", "theme for", "a theme for", "for", "generate a theme for", "generate theme for"]:
            if clean_prompt.startswith(prefix):
                brand_name = req.prompt[len(prefix):].strip()
                break
                
        brand_name = re.sub(r'^[^\w]+|[^\w]+$', '', brand_name).strip()
        if not brand_name:
            brand_name = "Custom Brand"
        else:
            brand_name = brand_name.title()
            
        # Match keywords
        if any(k in clean_prompt for k in ["coca-cola", "coca cola", "coke", "red"]):
            primary = "358, 100%, 47%"
            secondary = "0, 0%, 100%"
            bg_start = "#1a0002"
            bg_end = "#0d0001"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Ask me about retail volume, advertising conversion, or carbonation levels!"
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-red-600 fill-current'>"
                "<path d='M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z'/>"
                "<path d='M12 2v20'/>"
                "<path d='M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["john deere", "deere", "green", "farm", "tractor", "rustic"]):
            primary = "120, 100%, 25%"
            secondary = "48, 100%, 50%"
            bg_start = "#051205"
            bg_end = "#020802"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Let's analyze crop yields, equipment status, and parts distribution."
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-emerald-500'>"
                "<path d='M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z'/>"
                "<path d='M12 6v6l4 2'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["coffee", "starbucks", "cafe", "brew"]):
            primary = "155, 100%, 19%"
            secondary = "36, 44%, 60%"
            bg_start = "#030f0a"
            bg_end = "#010503"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. How can I help you query bean inventory and store metrics?"
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-emerald-700'>"
                "<path d='M18 8h1a4 4 0 0 1 0 8h-1'/>"
                "<path d='M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z'/>"
                "<line x1='6' y1='1' x2='6' y2='4'/>"
                "<line x1='10' y1='1' x2='10' y2='4'/>"
                "<line x1='14' y1='1' x2='14' y2='4'/>"
                "</svg>"
            )
        elif any(k in clean_prompt for k in ["home depot", "depot", "orange", "construction", "builder"]):
            primary = "23, 100%, 50%"
            secondary = "0, 0%, 100%"
            bg_start = "#1c0d02"
            bg_end = "#0d0601"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics. Let's analyze tool rentals, lumber prices, and regional warehouse stock."
            logo_svg = (
                "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-orange-500 fill-current'>"
                "<rect x='2' y='2' width='20' height='20' rx='3' />"
                "<text x='12' y='15' fill='white' font-size='9' font-weight='bold' font-family='sans-serif' text-anchor='middle'>HD</text>"
                "</svg>"
            )
        else:
            brand_hash = sum(ord(c) for c in brand_name)
            hue = brand_hash % 360
            primary = f"{hue}, 85%, 60%"
            secondary = f"{(hue + 180) % 360}, 85%, 55%"
            bg_start = "#0e0c14" if hue > 180 else "#0b0f13"
            bg_end = "#07060a" if hue > 180 else "#05080a"
            logo_text = brand_name.upper()
            welcome = f"Welcome to {brand_name} Analytics Workspace. Ask me anything about your analytics and data queries."
            if req.logo_url:
                logo_svg = f'<img src="{req.logo_url}" alt="{brand_name}" class="w-full h-full object-contain" />'
            else:
                logo_svg = (
                    "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' class='w-full h-full text-indigo-400'>"
                    "<polygon points='12 2 2 7 12 12 22 7 12 2'/>"
                    "<polyline points='2 17 12 22 22 17'/>"
                    "<polyline points='2 12 12 17 22 12'/>"
                    "</svg>"
                )
            
        if req.logo_url:
            logo_svg = f'<img src="{req.logo_url}" alt="{brand_name}" class="w-full h-full object-contain" />'
            
        return {
            "name": brand_name,
            "primaryColor": primary,
            "secondaryColor": secondary,
            "backgroundColorStart": bg_start,
            "backgroundColorEnd": bg_end,
            "logoText": logo_text,
            "welcomeMessage": welcome,
            "logoSvg": logo_svg
        }


@router.post("/api/branding/generate-greeting")
def generate_greeting(req: GenerateGreetingRequest, user: dict = Depends(get_current_user)):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    
    system_instruction = (
        "You are a branding assistant. Write a single, warm, professional, and customized data analytics greeting/welcome message "
        "for a company data portal of the brand provided. The message should greet users and suggest typical metrics/questions they "
        "can ask about (e.g. sales, inventory, store performance, etc.). Keep the message concise, under 25 words."
    )
    
    try:
        credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        session = AuthorizedSession(credentials)
        url = f"https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/publishers/google/models/gemini-1.5-flash:generateContent"
        
        payload = {
            "contents": [{"parts": [{"text": f"Write a greeting for the brand: {req.brand_name}"}]}],
            "generationConfig": {
                "temperature": 0.5
            },
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        
        resp = session.post(url, json=payload)
        if resp.status_code == 200:
            resp_data = resp.json()
            candidates = resp_data.get("candidates", [])
            if candidates:
                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text_content:
                    return {"welcomeMessage": text_content.strip()}
                    
        raise Exception(f"API status {resp.status_code}")
    except Exception as e:
        logger.warning(f"Error calling Gemini for greeting generation: {e}")
        return {
            "welcomeMessage": f"Welcome to {req.brand_name} Analytics. Ask me about sales volume, inventory, or performance metrics."
        }


@router.get("/api/branding/search-logo")
def search_logo(query: str, user: dict = Depends(get_current_user)):
    results = []
    clean_query = query.strip()
    if not clean_query:
        return results

    # 1. Speculative Domain Matching (helps find logos of custom/niche brands)
    if "." in clean_query:
        domain = clean_query.lower()
        results.append({
            "title": f"Domain: {domain}",
            "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={domain}&sz=128&default=404",
            "source": "Website Match"
        })
    else:
        spaced_removed = clean_query.replace(" ", "").lower()
        results.append({
            "title": f"Speculative: {spaced_removed}.com",
            "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={spaced_removed}.com&sz=128&default=404",
            "source": "Website Match"
        })
        if " " in clean_query:
            hyphenated = clean_query.replace(" ", "-").lower()
            results.append({
                "title": f"Speculative: {hyphenated}.com",
                "url": f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={hyphenated}.com&sz=128&default=404",
                "source": "Website Match"
            })

    # 2. Try Clearbit Autocomplete API (clean SVG/PNG company logos)
    try:
        response = requests.get(
            f"https://autocomplete.clearbit.com/v1/companies/suggest?query={requests.utils.quote(clean_query)}",
            timeout=5
        )
        if response.ok:
            data = response.json()
            for item in data:
                if item.get("domain"):
                    logo_url = f"/api/branding/logo-proxy?url=https://www.google.com/s2/favicons?domain={item['domain']}&sz=128&default=404"
                    if not any(r["url"] == logo_url for r in results):
                        results.append({
                            "title": item.get("name", clean_query),
                            "url": logo_url,
                            "source": "Verified Company"
                        })
    except Exception as e:
        logger.warning(f"Clearbit autocomplete failed: {e}")
    # 3. Try Wikipedia/Wikidata official logo query (works reliably on GCP/Cloud Run without blocking)
    try:
        import hashlib
        headers = {
            "User-Agent": "ConversationalAnalyticsPortal/1.0 (https://your-custom-domain.com; contact: support@your-custom-domain.com)"
        }
        # Strip TLD if it's a domain query to improve Wikipedia search matching (e.g. wonder.com -> wonder)
        wiki_query = clean_query
        if "." in wiki_query:
            parts = wiki_query.split(".")
            if len(parts) > 1 and parts[-1].lower() in ["com", "org", "net", "edu", "gov", "co", "io", "mil", "info", "biz", "app", "dev", "ai"]:
                wiki_query = " ".join(parts[:-1])

        search_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={requests.utils.quote(wiki_query)}&limit=3&namespace=0&format=json"
        wr = requests.get(search_url, headers=headers, timeout=5)
        if wr.ok:
            data = wr.json()
            titles = data[1]
            for title in titles:
                wiki_url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&sites=enwiki&titles={requests.utils.quote(title)}&props=claims&format=json"
                w_resp = requests.get(wiki_url, headers=headers, timeout=5)
                found_logo = False
                if w_resp.ok:
                    wdata = w_resp.json()
                    entities = wdata.get("entities", {})
                    for entity_id, entity_info in entities.items():
                        claims = entity_info.get("claims", {})
                        logo_claims = claims.get("P154", [])
                        if logo_claims:
                            filename = logo_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
                            if filename:
                                spaced_name = filename.replace(" ", "_")
                                md5_hash = hashlib.md5(spaced_name.encode('utf-8')).hexdigest()
                                logo_url = f"https://upload.wikimedia.org/wikipedia/commons/{md5_hash[0]}/{md5_hash[0:2]}/{spaced_name}"
                                results.append({
                                    "title": f"{title} Official Logo",
                                    "url": logo_url,
                                    "source": "Web Search"
                                })
                                found_logo = True
                                break
                
                # Fallback: Parse all images on the Wikipedia page looking for a matching logo
                if not found_logo:
                    img_list_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(title)}&prop=images&imlimit=100&format=json"
                    ir = requests.get(img_list_url, headers=headers, timeout=5)
                    if ir.ok:
                        idata = ir.json()
                        pages = idata.get("query", {}).get("pages", {})
                        for page_id, page_info in pages.items():
                            images = page_info.get("images", [])
                            exclude_patterns = [
                                "commons-logo", "wiktionary-logo", "wikimedia-logo", "wikipedia-logo",
                                "wikiquote-logo", "wikidata-logo", "wikisource-logo", "wikibooks-logo",
                                "wikinews-logo", "wikiversity-logo", "wikivoyage-logo", "mediawiki-logo",
                                "disambig", "stub", "edit-clear", "question_book", "lock", "padlock",
                                "icon", "search-logo", "external_link", "decrease", "increase", "symbol"
                            ]
                            candidates = []
                            for img in images:
                                img_title = img.get("title", "")
                                img_lower = img_title.lower()
                                if "logo" in img_lower:
                                    excluded = False
                                    for pattern in exclude_patterns:
                                        if pattern in img_lower:
                                            excluded = True
                                            break
                                    if not excluded:
                                        candidates.append(img_title)
                            
                            if candidates:
                                # Score candidates
                                best_candidate = None
                                best_score = -100.0
                                import re
                                query_words = [w for w in re.split(r'\W+', clean_query.lower()) if len(w) > 2]
                                
                                for cand in candidates:
                                    cand_lower = cand.lower()
                                    score = 0
                                    for qw in query_words:
                                        if qw in cand_lower:
                                            score += 1
                                    
                                    title_clean = title.lower().replace("corporation", "").replace("group", "").replace("inc", "").strip()
                                    title_words = [w for w in re.split(r'\W+', title_clean) if len(w) > 2]
                                    for tw in title_words:
                                        if tw in cand_lower:
                                            score += 2
                                    
                                    if cand_lower.endswith(".svg"):
                                        score += 1.5
                                        
                                    year_match = re.search(r'(18|19|20)\d{2}', cand_lower)
                                    if year_match:
                                        year = int(year_match.group(0))
                                        score -= (2026 - year) * 0.5 + 2.0
                                        
                                    for keyword in ["historical", "old", "history"]:
                                        if keyword in cand_lower:
                                            score -= 5.0
                                            
                                    score -= len(cand) * 0.005
                                    
                                    if score > best_score:
                                        best_score = score
                                        best_candidate = cand
                                
                                if not best_candidate:
                                    best_candidate = candidates[0]
                                    
                                # Resolve URL of selected candidate
                                info_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(best_candidate)}&prop=imageinfo&iiprop=url&format=json"
                                infor = requests.get(info_url, headers=headers, timeout=5)
                                if infor.ok:
                                    infodata = infor.json()
                                    infopages = infodata.get("query", {}).get("pages", {})
                                    for ipage_id, ipage_info in infopages.items():
                                        info_list = ipage_info.get("imageinfo", [])
                                        if info_list:
                                            resolved_logo_url = info_list[0].get("url")
                                            results.append({
                                                "title": f"{title} Official Logo",
                                                "url": resolved_logo_url,
                                                "source": "Web Search"
                                            })
                                            found_logo = True
                                            break
                            if found_logo:
                                break
                if found_logo:
                    break
    except Exception as e:
        logger.warning(f"Wikipedia logo retrieval failed: {e}")

    # 4. Try Google Image Search (public scrape) as fallback or secondary results
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}+logo&tbm=isch&safe=active"
        res = requests.get(search_url, headers=headers, timeout=5)
        if res.ok:
            import re
            matches = re.findall(r'src="(https://encrypted-tbn0\.gstatic\.com/images\?q=[^"]+)"', res.text)
            for idx, img_url in enumerate(matches[:15]):
                if not any(r["url"] == img_url for r in results):
                    results.append({
                        "title": query.title(),
                        "url": img_url,
                        "source": "Web Search"
                    })
    except Exception as e:
        logger.warning(f"Google Image scrape failed: {e}")
        
    return results


@router.get("/api/branding/logo-proxy")
def logo_proxy(url: str = Query(...)):
    allowed_prefixes = (
        "https://www.google.com/s2/favicons",
        "https://t0.gstatic.com/",
        "https://t1.gstatic.com/",
        "https://t2.gstatic.com/",
        "https://t3.gstatic.com/",
        "https://logo.clearbit.com/"
    )
    if not url.startswith(allowed_prefixes):
        raise HTTPException(status_code=400, detail="Invalid proxy target")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if not res.ok:
            return Response(status_code=404)
            
        import hashlib
        md5_hash = hashlib.md5(res.content).hexdigest()
        FALLBACK_GLOBE_MD5S = {
            "b8a0bf372c762e966cc99ede8682bc71",  # 726-byte blue globe
            "bd292eb2e8187dd045a7d1ddf15b7f5a"   # 413-byte blue globe
        }
        if md5_hash in FALLBACK_GLOBE_MD5S:
            return Response(status_code=404)
            
        return Response(content=res.content, media_type=res.headers.get("Content-Type", "image/png"))
    except Exception as e:
        logger.warning(f"Failed to proxy logo URL {url}: {e}")
        return Response(status_code=404)


@router.get("/api/branding")
def get_branding(user: dict = Depends(get_current_user)):
    try:
        # 1. Try to load from Firestore first
        branding_data = None
        try:
            db = firestore.client()
            doc_ref = db.collection("settings").document("branding")
            doc = doc_ref.get()
            if doc.exists:
                branding_data = doc.to_dict()
                # Also save locally as a fallback
                try:
                    os.makedirs(FRONTEND_DIR, exist_ok=True)
                    with open(BRANDING_FILE, "w") as f:
                        json.dump(branding_data, f, indent=2)
                except Exception as e:
                    logger.warning(f"Failed to write branding fallback file: {e}")
        except Exception as fe:
            logger.warning(f"Could not load branding from Firestore: {fe}. Falling back to local file.")

        # 2. Fallback to local file
        if not branding_data and os.path.exists(BRANDING_FILE):
            with open(BRANDING_FILE, "r") as f:
                branding_data = json.load(f)
                
        if not branding_data:
            # Return default branding configuration
            branding_data = {
                "activeBrand": "default",
                "brands": {
                    "default": {
                        "name": "Google Cloud",
                        "primaryColor": "217, 89%, 61%",
                        "secondaryColor": "142, 70%, 45%",
                        "backgroundColorStart": "#0b0f19",
                        "backgroundColorEnd": "#1a2333",
                        "welcomeMessage": "Welcome to your data assistant. How can I help you analyze your databases today?",
                        "logoUrl": "",
                        "logoText": "Google Cloud Analytics",
                        "logoSvg": "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 35 32' class='w-full h-full'><path fill='#ea4335' d='M21.85,7.41l1,0,2.85-2.85.14-1.21A12.81,12.81,0,0,0,5,9.6a1.55,1.55,0,0,1,1-.06l5.7-.94s.29-.48.44-.45a7.11,7.11,0,0,1,9.73-.74Z'/><path fill='#4285f4' d='M29.76,9.6a12.84,12.84,0,0,0-3.87-6.24l-4,4A7.11,7.11,0,0,1,24.5,13v.71a3.56,3.56,0,1,1,0,7.12H17.38l-.71.72v4.27l.71.71H24.5A9.26,9.26,0,0,0,29.76,9.6Z'/><path fill='#34a853' d='M10.25,26.49h7.12v-5.7H10.25a3.54,3.54,0,0,1-1.47-.32l-1,.31L4.91,23.63l-.25,1A9.21,9.21,0,0,0,10.25,26.49Z'/><path fill='#fbbc05' d='M10.25,8A9.26,9.26,0,0,0,4.66,24.6l4.13-4.13a3.56,3.56,0,1,1,4.71-4.71l4.13-4.13A9.25,9.25,0,0,0,10.25,8Z'/></svg>"
                    }
                }
            }

        # 3. Dynamic Default Injection! (Ensure active brand always has resolved GCP settings)
        active_brand = branding_data.get("activeBrand", "default")
        if "brands" in branding_data and active_brand in branding_data["brands"]:
            brand_settings = branding_data["brands"][active_brand]
            modified = False
            if "gcpProjectId" not in brand_settings or not brand_settings["gcpProjectId"]:
                try:
                    brand_settings["gcpProjectId"] = get_project_id()
                    modified = True
                except Exception:
                    pass
            if "gcpLocation" not in brand_settings or not brand_settings["gcpLocation"]:
                try:
                    brand_settings["gcpLocation"] = get_location()
                    modified = True
                except Exception:
                    brand_settings["gcpLocation"] = "global"
                    modified = True

            # If we modified the branding data by injecting defaults, auto-sync and write it back to Firestore!
            if modified:
                try:
                    db = firestore.client()
                    doc_ref = db.collection("settings").document("branding")
                    doc_ref.set(branding_data)
                    logger.info("Automatically synchronized and saved resolved GCP defaults to Firestore branding document.")
                except Exception as save_err:
                    logger.warning(f"Could not auto-sync resolved GCP defaults to Firestore: {save_err}")

        return branding_data
    except Exception as e:
        logger.error(f"Error fetching branding: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve branding settings.")


@router.post("/api/branding")
def save_branding(data: dict = Body(...), user: dict = Depends(get_current_user)):
    try:
        # 1. Try to save in Firestore first
        firestore_saved = False
        try:
            db = firestore.client()
            doc_ref = db.collection("settings").document("branding")
            doc_ref.set(data)
            logger.info("Successfully saved branding settings in Firestore.")
            firestore_saved = True
        except Exception as fe:
            logger.warning(f"Could not save branding to Firestore: {fe}. Saving only to local file.")

        # 2. Save to local file
        os.makedirs(FRONTEND_DIR, exist_ok=True)
        with open(BRANDING_FILE, "w") as f:
            json.dump(data, f, indent=2)
            
        # Log to Firestore audit log
        log_audit_to_firestore(
            user_email=user.get("email", "unknown"),
            event_type="BRANDING_UPDATE",
            details={"activeBrand": data.get("activeBrand"), "firestore_sync": firestore_saved}
        )
        
        return {"status": "success", "message": "Branding updated successfully"}
    except Exception as e:
        logger.error(f"Error saving branding: {e}")
        raise HTTPException(status_code=500, detail="Failed to save branding configurations.")



