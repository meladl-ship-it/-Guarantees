
import os

src = r"F:\‏‏Guarantees\templates\table.html"
dst = r"F:\‏‏Guarantees\نسخة 1\templates\table.html"

try:
    with open(src, 'r', encoding='utf-8') as f:
        content = f.read()
    
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print(f"Successfully synced {src} to {dst}")
except Exception as e:
    print(f"Error: {e}")
