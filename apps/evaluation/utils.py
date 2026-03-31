import subprocess

def evaluate_code_glot(language_key, source_code, stdin_data):
    try:
        # Run the code using a subprocess with a 5-second timeout
        # 'python3' is usually available in Django Docker image
        process = subprocess.Popen(
            ['python3', '-c', source_code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=stdin_data, timeout=5)
        
        return {
            "stdout": stdout,
            "stderr": stderr,
            "error": None
        }
    except subprocess.TimeoutExpired:
        process.kill()
        return {"error": "Time Limit Exceeded", "stderr": "Code took too long to run."}
    except Exception as e:
        return {"error": str(e), "stderr": ""}

# import subprocess
# import os
# import resource
# import pwd

# def limit_resources():
#     """Sets OS-level hard limits on the child process."""
#     # 2 seconds of CPU time
#     resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
#     # 128MB Max Virtual Memory
#     resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
#     # Max 10 child processes (Prevents Fork Bombs)
#     resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
#     # Max file size creation: 1MB
#     resource.setrlimit(resource.RLIMIT_FSIZE, (1 * 1024 * 1024, 1 * 1024 * 1024))

# def is_code_malicious(source_code):
#     """Basic string-based defense for common 'jailbreak' attempts."""
#     forbidden = [
#         'os.', 'subprocess', 'pty', 'socket', 'requests', 'urllib', 
#         'getattr', 'eval(', 'exec(', '__builtins__', 'SECRET_KEY', 'DATABASE'
#     ]
#     code_lower = source_code.lower()
#     for word in forbidden:
#         if word.lower() in code_lower:
#             return True, f"Security Violation: '{word}' is not allowed."
#     return False, ""

# def evaluate_code_securely(source_code, stdin_data):
#     # 1. String Check
#     malicious, message = is_code_malicious(source_code)
#     if malicious:
#         return {"stdout": "", "stderr": message, "error": "Security Block"}

#     # 2. Clean Environment (Totally isolated from Render/Django secrets)
#     safe_env = {
#         "PATH": "/usr/bin:/bin",
#         "LANG": "en_US.UTF-8",
#         "PYTHONPATH": "/tmp", 
#         "HOME": "/home/sandboxuser"
#     }

#     try:
#         # Get the UID for the sandbox user created in Dockerfile
#         # If testing locally without the user, comment the 'user' line
#         try:
#             sandbox_uid = pwd.getpwnam("sandboxuser").pw_uid
#         except KeyError:
#             sandbox_uid = None # Fallback for local dev environments

#         # 3. Execution with full isolation
#         process = subprocess.Popen(
#             ['python3', '-c', source_code],
#             stdin=subprocess.PIPE,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#             env=safe_env,           # Blocks secret keys
#             cwd='/tmp',             # Moves context away from /app
#             user=sandbox_uid,       # Runs as low-privilege user
#             preexec_fn=limit_resources # Handcuffs CPU/RAM/Processes
#         )

#         stdout, stderr = process.communicate(input=stdin_data, timeout=5)

#         return {
#             "stdout": stdout,
#             "stderr": stderr,
#             "error": None
#         }

#     except subprocess.TimeoutExpired:
#         process.kill()
#         return {"error": "Time Limit Exceeded", "stderr": "Process killed after 5s."}
#     except Exception as e:
#         return {"error": "System Error", "stderr": str(e)}