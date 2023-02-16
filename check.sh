#!/bin/bash

# this assumes that all project dependencies, as well as all dev dependencies
# (e.g. flake8 and mypy) have already been installed, e.g. via:
#    pip install -r requrements.txt
#    pip install -r requrements-dev.txt

# flake8 and mypy config options are specified in setup.cfg

# colored output: https://www.tutorialspoint.com/how-to-output-colored-text-to-a-linux-terminal
red="\033[1;31m"
green="\033[1;32m"
normal="\033[0m"
pass="${green}PASS${normal}"
fail="${red}FAIL${normal}"

# set to a non-zero value if any check returns a non-zero value
check_result=0

echo "Run flake8 style checks"
echo "flake8 slack2discord.py slack2discord"
flake8 slack2discord.py slack2discord
# XXX not really, I just want to test both pass and fail right now
true
flake8_result=$?
if [[ $flake8_result -eq 0 ]]; then
   echo -e "flake8: \033[1;32m PASS \033[0m"
   echo -e "flake8: \033[1;32mPASS\033[0m"
   echo "flake8: PASS"
   echo -e "flake8: $pass"
   echo "flake8: $pass"
else
   echo -e "flake8: \033[1;31m FAIL \033[0m"
   echo -e "flake8: \033[1;31mFAIL\033[0m"
   echo "flake8: FAIL"
   echo -e "flake8: $fail"
   echo "flake8: $fail"
   check_result=1
fi

echo
echo "Run mypy static typing checks"
echo "mypy slack2discord.py"
mypy slack2discord.py
mypy_result=$?
if [[ $mypy_result -eq 0 ]]; then
   echo -e "mypy: \033[1;32m PASS \033[0m"
   echo -e "mypy: \033[1;32mPASS\033[0m"
   echo "mypy: PASS"
   echo -e "mypy: $pass"
   echo "mypy: $pass"
else
   echo -e "mypy: \033[1;31m FAIL \033[0m"
   echo -e "mypy: \033[1;31mFAIL\033[0m"
   echo "mypy: FAIL"
   echo -e "mypy: $fail"
   echo "mypy: $fail"
   check_result=1
fi

echo
if [[ $check_result -eq 0 ]]; then
   echo "Union of all checks: PASS"
else
   echo "Union of all checks: FAIL"
fi

exit $check_result
