# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A module to handle running fuzz targets for a specified amount of time."""
import datetime
import enum
import logging
import subprocess
import os
import re
import signal
import sys
import time

import helper

class FuzzTarget():
  """A class to manage a single fuzz target.

  Attributes:
    project_name: The name of the OSS-Fuzz project this target is associated with.
    target_name: The name of the fuzz target.
    duration: The length of time in seconds that the target should run.
  """

  def __init__(self, project_name, target_path, duration):
    """Represents a single fuzz target.

    Args:
      project_name: The OSS-Fuzz project of this target.
      target_path: The location of the fuzz target binary.
      duration: The length of time  in seconds the target should run.
    """
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', stream=sys.stdout, level=logging.DEBUG)
    self.target_name = target_path.split('/')[-1]
    self.duration = duration
    self.project_name = project_name

  def start(self):
    """Starts the fuzz target run for the length of time specifed by duration.

    Returns:
      (test_case, stack trace) if found or (None, None) on timeout or error.
    """
    command = ['docker', 'run', '--rm', '--privileged']

    env = [
        'FUZZING_ENGINE=libfuzzer',
        'SANITIZER=address',
        'RUN_FUZZER_MODE=interactive',
    ]
    run_args = helper._env_to_docker_args(env) + [
        '-v', '%s:/out' % helper._get_output_dir(self.project_name),
        '-t', 'gcr.io/oss-fuzz-base/base-runner',
        'run_fuzzer',
        self.target_name,
    ]

    command.extend(run_args)
    logging.debug('Running command: {}'.format(' '.join(command)))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
      out, err = process.communicate(timeout=self.duration)
    except subprocess.TimeoutExpired:
      logging.debug('Fuzzer {} finished with timeout.'.format(self.target_name))
      return None, None
    output = out.decode('ascii')
    test_case = self.get_test_case(output)
    if not test_case:
      print('Error no test case found in stack trace.', file=sys.stderr)
      return None, None
    return test_case, output

  def get_test_case(self, error_string):
    """Gets the file from a fuzzer run stack trace.

    Args:
      error_string: The stack trace string containing the error.

    Returns:
      The error testcase or None if not found
    """
    match = re.search(r'\bTest unit written to \.([^ ]+)', error_string.rstrip())
    if match:
      return os.path.join(helper.BUILD_DIR,'out', self.project_name, match.group(1))
    return None