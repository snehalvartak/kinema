@echo off
cd /d "%~dp0.."
python -u benchmark\feedback_arm.py --arm feedback --models z-ai/glm-5.3-flash z-ai/glm-5.2 z-ai/glm-4.5-air
python -u benchmark\feedback_arm.py --arm hybrid --models z-ai/glm-5.3-flash z-ai/glm-5.2 z-ai/glm-4.5-air
