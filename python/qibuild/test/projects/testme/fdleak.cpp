/*
 * Copyright (c) 2012-2018 SoftBank Robotics. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the COPYING file.
 */
#include <fcntl.h>

int main() {
  int f = open("/dev/zero", O_RDONLY);
  return 0;
}
