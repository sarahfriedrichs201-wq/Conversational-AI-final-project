import os

from google import genai
from google.genai import types
from typing import Dict, List, Optional, Any

from openai import OpenAI

def generate_gemini(prompt: str, instance_id: str, model: str, system_instruct: str):
    # Initialize Gemini client (uses GEMINI_API_KEY env var)
    client = genai.Client()
    
    print(f"  [Gemini] Generating patch for {instance_id}...")
    
    response = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system_instruct,
            temperature=0.2,  # Lower temperature for more consistent output
        ),
        contents=prompt
    )
    
    return(response.text)

def generate_deepseek(prompt: str, instance_id: str, model: str, system_instruct: str):
    
    client = OpenAI(api_key=os.environ.get('DEEPSEEK_API_KEY'), base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_instruct},
            {"role": "user", "content": prompt},
        ],
    stream=False
    )

    return(response.choices[0].message.content)

def generate_doc(prompt: str, instance_id: str, model_type: str, model: str, system_instruct: str) -> Optional[str]:
    """
    Generate a document using the specified model.
    
    Args:
        prompt: The formatted prompt
        instance_id: Instance ID for logging
        model_type: ["gemini", "deepseek"]
        model: Specific model type
        system_instruct: System instruction for the model
        
    Returns:
        Generated patch string or None if failed
    """
    try:
        # Call each model
        if model_type == "gemini":
            doc_text = generate_gemini(prompt, instance_id, model, system_instruct)
        
        if model_type == "deepseek":
            doc_text = generate_deepseek(prompt, instance_id, model, system_instruct)
        
        if not doc_text:
            print(f"  [WARN] Empty response for {instance_id}")
            return None
        
        return doc_text
        
    except Exception as e:
        print(f"  [ERROR] API failed for {instance_id}: {e}")
        return None

def generate_patch(prompt: str, instance_id: str, model_type: str, model: str, system_instruct: str) -> Optional[str]:
    """
    Generate a patch using specified model.
    
    Args:
        prompt: The formatted prompt
        instance_id: Instance ID for logging
        model_type: ["gemini", "deepseek"]
        model: Specific model type
        system_instruct: System instruction for the model
        
    Returns:
        Generated patch string or None if failed
    """
    try:
        # Call each model
        if model_type == "gemini":
            patch_text = generate_gemini(prompt, instance_id, model, system_instruct)
        
        if model_type == "deepseek":
            patch_text = generate_deepseek(prompt, instance_id, model, system_instruct)
        
        if not patch_text:
            print(f"  [WARN] Empty response for {instance_id}")
            return None
        
        # Basic validation that it looks like a patch
        if "diff --git" not in patch_text:
            print(f"  [WARN] Response doesn't look like a git diff for {instance_id}")
            # Try to extract patch if it's wrapped in code blocks
            if "```" in patch_text:
                lines = patch_text.split("\n")
                in_code_block = False
                extracted_lines = []
                for line in lines:
                    if line.strip().startswith("```"):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block:
                        extracted_lines.append(line)
                if extracted_lines and "diff --git" in "\n".join(extracted_lines):
                    patch_text = "\n".join(extracted_lines)
                    print(f"  [INFO] Extracted patch from code block")
        
        return patch_text
        
    except Exception as e:
        print(f"  [ERROR] API failed for {instance_id}: {e}")
        return None


def save_patch(patch_text: str, task: Dict[str, Any], OUTPUT_DIR) -> str:
    """
    Save generated patch to disk.
    
    Args:
        patch_text: The patch content
        task: Task dictionary with metadata
        
    Returns:
        Path to saved patch file
    """
    # Create output directory structure
    repo_slug = task["repo"].replace("/", "__")
    instance_id = task["instance_id"]
    
    output_subdir = OUTPUT_DIR / repo_slug
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    patch_file = output_subdir / f"{instance_id}.patch"
    
    with open(patch_file, "w") as f:
        f.write(patch_text)
    
    print(f"  [SAVED] Patch saved to {patch_file}")
    return str(patch_file)

def save_doc(doc_text: str, task: Dict[str, Any], output_dir) -> str:
    """
    Save generated doc to disk.
    
    Args:
        doc_text: The doc content
        task: Task dictionary with metadata
        
    Returns:
        Path to saved doc file
    """
    # Create output directory structure
    repo_slug = task["repo"].replace("/", "__")
    instance_id = task["instance_id"]
    
    output_subdir = output_dir / repo_slug
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    doc_file = output_subdir / f"{instance_id}.txt"
    
    with open(doc_file, "w") as f:
        f.write(doc_text)
    
    print(f"  [SAVED] document saved to {doc_file}")
    return str(doc_file)