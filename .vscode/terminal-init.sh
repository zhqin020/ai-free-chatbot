#!/bin/bash
# Project-specific terminal initialization for aifree
# This file is only sourced by VS Code terminals in this workspace

# First, source user's bashrc to load their configurations
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Then initialize conda and activate aifree (this will set the prompt correctly)
if [ -f ~/miniconda3/etc/profile.d/conda.sh ]; then
    # Initialize conda
    source ~/miniconda3/etc/profile.d/conda.sh
    
    # Activate aifree environment (suppress error messages if already activated)
    if [ "$CONDA_DEFAULT_ENV" != "aifree" ]; then
        conda activate aifree 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "✓ aifree environment activated"
        fi
    fi
fi
