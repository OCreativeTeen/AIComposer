#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
REST API Utility Module
Provides reusable REST API functionality for making HTTP requests with multipart form data.
"""

import requests
import os
from typing import Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)



