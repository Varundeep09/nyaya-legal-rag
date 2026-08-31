"""
Script to discover real available Google Gemini models using the active API key.
Validates credentials, queries the live Gemini API, lists available models,
and tests generation with the primary flash-tier model.
"""

import sys
import os

# Ensure UTF-8 output on Windows terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import google.generativeai as genai
from app.core.config import settings


def discover_gemini_models():
    print("=" * 80)
    print("          GOOGLE GEMINI MODEL DISCOVERY & VALIDATION SCRIPT            ")
    print("=" * 80)

    api_key = settings.GEMINI_API_KEY
    if not api_key or api_key in ("your_gemini_api_key_here", "dev-secret-key-change-in-production"):
        print("\n[FATAL ERROR] GEMINI_API_KEY is not set or is set to a placeholder value!")
        print("Please set a real Google Gemini API key in your .env file or GEMINI_API_KEY environment variable.")
        print("Example in .env:")
        print("  GEMINI_API_KEY=AQ.Ab8...")
        print("=" * 80)
        sys.exit(1)

    print(f"[*] API Key detected: {api_key[:6]}...{api_key[-4:] if len(api_key) > 10 else ''}")
    print("[*] Configuring google.generativeai SDK...")
    genai.configure(api_key=api_key)

    print("[*] Querying live Gemini API for supported models (genai.list_models())...\n")
    try:
        all_models = list(genai.list_models())
    except Exception as e:
        print(f"\n[FATAL ERROR] Failed to query Gemini API with provided key: {e}")
        print("Check if the key is valid, active, and has access to Gemini API.")
        print("=" * 80)
        sys.exit(1)

    content_models = [m for m in all_models if "generateContent" in m.supported_generation_methods]
    flash_models = [m for m in content_models if "flash" in m.name.lower()]

    print(f"Total Models Returned: {len(all_models)}")
    print(f"Models Supporting generateContent: {len(content_models)}")
    print(f"Flash-Tier (Free-Tier Eligible) Models: {len(flash_models)}\n")

    print("-" * 80)
    print(f"{'Model Name':<42} | {'Display Name':<25} | {'Flash?':<8}")
    print("-" * 80)
    for m in content_models:
        is_flash = "YES (Flash)" if "flash" in m.name.lower() else "No"
        display_name = m.display_name or "N/A"
        print(f"{m.name:<42} | {display_name[:25]:<25} | {is_flash:<8}")
    print("-" * 80)

    # Preferred active models in order of freshness
    candidate_order = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-flash-latest"]
    
    target_model_name = None
    for cand in candidate_order:
        if any(cand in m.name for m in content_models):
            target_model_name = cand
            break

    if not target_model_name:
        target_model_name = flash_models[0].name.replace("models/", "") if flash_models else content_models[0].name.replace("models/", "")

    clean_model_name = target_model_name.replace("models/", "")
    print(f"\n[+] Selected Real Gemini Model: '{clean_model_name}'")

    # Live verification call
    print(f"\n[*] Executing live verification call to '{clean_model_name}'...")
    try:
        model = genai.GenerativeModel(model_name=clean_model_name)
        response = model.generate_content("Respond with exactly: 'Gemini live connection verified.'")
        
        print("\n" + "=" * 80)
        print("                     LIVE API RESPONSE PROOF                           ")
        print("=" * 80)
        print(f" Model Used:        {clean_model_name}")
        print(f" Response Text:     {response.text.strip()!r}")
        
        # Check candidate metadata
        if response.candidates:
            cand = response.candidates[0]
            print(f" Finish Reason:     {cand.finish_reason}")
            print(f" Safety Ratings:    {len(cand.safety_ratings)} ratings returned")
            
        # Check usage metadata
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            u = response.usage_metadata
            print(f" Prompt Tokens:     {u.prompt_token_count}")
            print(f" Candidate Tokens:  {u.candidates_token_count}")
            print(f" Total Tokens:      {u.total_token_count}")
        print("=" * 80)
        print("\n[SUCCESS] Real Google Gemini API connection confirmed working!")
        return clean_model_name
    except Exception as e:
        print(f"\n[ERROR] Live test call failed on model '{clean_model_name}': {e}")
        sys.exit(1)


if __name__ == "__main__":
    discover_gemini_models()
