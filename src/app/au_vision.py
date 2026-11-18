#!/usr/bin/env python3
"""
AU Screen Vision & Native OCR Engine
Provides 100% offline, Apple Neural Engine-accelerated screen reading and visual comprehension.
Uses macOS native `screencapture` + compiled Apple Vision Framework (`tools/au-ocr`).
"""

import os
import sys
import subprocess
import tempfile
from typing import Optional, Dict, Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OCR_TOOL = os.path.join(PROJECT_ROOT, "tools", "au-ocr")

class AUScreenVision:
    def __init__(self, ocr_tool_path: str = OCR_TOOL):
        self.ocr_tool = ocr_tool_path
        if not os.path.exists(self.ocr_tool):
            # Fallback path if run from src/app
            alt_path = os.path.join(SCRIPT_DIR, "..", "..", "tools", "au-ocr")
            if os.path.exists(alt_path):
                self.ocr_tool = os.path.abspath(alt_path)

    def capture_screen(self, output_path: Optional[str] = None, window_only: bool = False) -> str:
        """Captures the macOS display silently without flash or sound."""
        if not output_path:
            output_path = os.path.join(tempfile.gettempdir(), "au_screen_capture.png")

        cmd = ["screencapture", "-x"]
        if window_only:
            cmd.append("-w")
        cmd.append(output_path)

        try:
            subprocess.run(cmd, check=True, timeout=5)
            return output_path
        except Exception as e:
            raise RuntimeError(f"Screen capture failed: {e}")

    def extract_text_from_image(self, image_path: str) -> str:
        """Extracts text from any image using Apple's native Vision framework OCR."""
        if not os.path.exists(self.ocr_tool):
            return "Error: au-ocr tool binary not found."

        try:
            res = subprocess.run([self.ocr_tool, image_path], capture_output=True, text=True, timeout=10)
            return res.stdout.strip()
        except Exception as e:
            return f"Error executing Vision OCR: {e}"

    def read_screen_text(self) -> str:
        """Captures active screen and extracts all visible text via Vision OCR."""
        img_path = self.capture_screen()
        return self.extract_text_from_image(img_path)

    def analyze_screen(self, query: str = "Explain what is on the screen", orchestrator=None) -> Dict[str, Any]:
        """
        Captures screen, extracts visible text with Vision OCR, and grounds the local LLM
        to answer the user's visual question.
        """
        img_path = self.capture_screen()
        screen_text = self.extract_text_from_image(img_path)

        if not screen_text:
            return {
                "text": "I captured your screen, but could not detect any readable text.",
                "screen_text": "",
                "image_path": img_path
            }

        prompt = (
            f"The user took a screenshot of their Mac screen. Here is the exact text detected on their display:\n\n"
            f"```text\n{screen_text[:3500]}\n```\n\n"
            f"User Question: {query}\n"
            f"Analyze what the user is looking at and answer their question clearly, precisely, and helpfully."
        )

        return {
            "prompt": prompt,
            "screen_text": screen_text,
            "image_path": img_path
        }

if __name__ == "__main__":
    vision = AUScreenVision()
    print("Capturing screen and performing Apple Vision OCR...")
    text = vision.read_screen_text()
    print(f"Recognized {len(text)} characters of text from screen.")
    print("Sample:\n" + "\n".join(text.splitlines()[:10]))
