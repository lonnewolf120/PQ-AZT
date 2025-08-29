#!/bin/bash
set -e

# Update system
sudo apt update && sudo apt upgrade

# Download and install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p $HOME/miniconda
eval "$($HOME/miniconda/bin/conda shell.bash hook)"

# Initialize conda for future shells
conda init bash

# Create conda environment
conda create -y --name thesis python=3.10

# Activate environment
conda activate thesis

# Install dependencies
conda install -y pip
pip install qiskit jupyter matplotlib qiskit-ibm-runtime pylatexenc

# Run Jupyter Lab
jupyter lab
