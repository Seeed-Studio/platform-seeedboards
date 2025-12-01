

def configure_esp_default_packages(self, variables, targets):
    print("esp configure_default_packages")

    board_config = self.board_config(variables.get("board"))
    mcu = variables.get("board_build.mcu", board_config.get("build.mcu", "esp32"))
    
    self.packages["framework-arduinoespressif32"]["optional"] = False
    self.packages["esp32-arduino-libs"]["optional"] = False
    self.packages["tool-esptoolpy"]["optional"] = False
    
    # Enable check tools only when "check_tool" is enabled
    # self.packages里就是json文件中的所有 packages 项
    for p in self.packages:
        if p in ("tool-cppcheck", "tool-clangtidy", "tool-pvs-studio"):
            self.packages[p]["optional"] = False if str(variables.get("check_tool")).strip("['']") in p else True
            print(self.packages[p]["optional"])

    #设置 tool-xtensa-esp-elf-gdb 与 tool-riscv32-esp-elf-gdb 两个工具链为必选项
    for gdb_package in ("tool-xtensa-esp-elf-gdb", "tool-riscv32-esp-elf-gdb"):
        self.packages[gdb_package]["optional"] = False
        # if IS_WINDOWS:
            # Note: On Windows GDB v12 is not able to
            # launch a GDB server in pipe mode while v11 works fine
            # self.packages[gdb_package]["version"] = "~11.2.0"

    # 如果是 "esp32", "esp32s2", "esp32s3" 则必须使用 toolchain-xtensa-esp-elf 工具链，不是这几款就不用 toolchain-xtensa-esp-elf，把toolchain-xtensa-esp-elf删除
    if mcu in ("esp32", "esp32s2", "esp32s3"):
        self.packages["toolchain-xtensa-esp-elf"]["optional"] = False
    else:
        print("pop toolchain-xtensa-esp-elf")
        self.packages.pop("toolchain-xtensa-esp-elf", None)

    if mcu in ("esp32s2", "esp32s3", "esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32h2", "esp32p4"):
        if mcu in ("esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32h2", "esp32p4"):
            self.packages.pop("toolchain-esp32ulp", None)
        # RISC-V based toolchain for ESP32C3, ESP32C6 ESP32S2, ESP32S3 ULP
        self.packages["toolchain-riscv32-esp"]["optional"] = False







def _add_esp_default_debug_tools(self, board):
    # print("in _add_default_esp_debug_tools")
    # upload protocols
    if not board.get("upload.protocols", []):
        board.manifest["upload"]["protocols"] = ["esptool", "espota"]
    if not board.get("upload.protocol", ""):
        board.manifest["upload"]["protocol"] = "esptool"

    # debug tools
    debug = board.manifest.get("debug", {})
    non_debug_protocols = ["esptool", "espota"]
    supported_debug_tools = [
        "cmsis-dap",
        "esp-prog",
        "esp-bridge",
        "iot-bus-jtag",
        "jlink",
        "minimodule",
        "olimex-arm-usb-tiny-h",
        "olimex-arm-usb-ocd-h",
        "olimex-arm-usb-ocd",
        "olimex-jtag-tiny",
        "tumpa",
    ]


    if board.get("build.mcu", "") in ("esp32c3", "esp32c6", "esp32s3", "esp32h2"):
        supported_debug_tools.append("esp-builtin")

    upload_protocol = board.manifest.get("upload", {}).get("protocol")
    upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
    if debug:
        upload_protocols.extend(supported_debug_tools)
    if upload_protocol and upload_protocol not in upload_protocols:
        upload_protocols.append(upload_protocol)
    board.manifest["upload"]["protocols"] = upload_protocols

    if "tools" not in debug:
        debug["tools"] = {}

    for link in upload_protocols:
        if link in non_debug_protocols or link in debug["tools"]:
            continue

        if link in ("jlink", "cmsis-dap"):
            openocd_interface = link
        elif link in ("esp-prog", "ftdi"):
            openocd_interface = "ftdi/esp32_devkitj_v1"
        elif link == "esp-bridge":
            openocd_interface = "esp_usb_bridge"
        elif link == "esp-builtin":
            openocd_interface = "esp_usb_jtag"
        else:
            openocd_interface = "ftdi/" + link

        server_args = [
            "-s",
            "$PACKAGE_DIR/share/openocd/scripts",
            "-f",
            "interface/%s.cfg" % openocd_interface,
            "-f",
            "%s/%s"
            % (
                ("target", debug.get("openocd_target"))
                if "openocd_target" in debug
                else ("board", debug.get("openocd_board"))
            ),
        ]

        debug["tools"][link] = {
            "server": {
                "package": "tool-openocd-esp32",
                "executable": "bin/openocd",
                "arguments": server_args,
            },
            "init_break": "thb app_main",
            "init_cmds": [
                "define pio_reset_halt_target",
                "   monitor reset halt",
                "   flushregs",
                "end",
                "define pio_reset_run_target",
                "   monitor reset",
                "end",
                "target extended-remote $DEBUG_PORT",
                "$LOAD_CMDS",
                "pio_reset_halt_target",
                "$INIT_BREAK",
            ],
            "onboard": link in debug.get("onboard_tools", []),
            "default": link == debug.get("default_tool"),
        }


    board.manifest["debug"] = debug
    return board



def configure_esp_debug_session(self, debug_config):
    print("in configure_esp_debug_session")
    build_extra_data = debug_config.build_data.get("extra", {})
    flash_images = build_extra_data.get("flash_images", [])

    if "openocd" in (debug_config.server or {}).get("executable", ""):
        debug_config.server["arguments"].extend(
            ["-c", "adapter speed %s" % (debug_config.speed or "5000")]
        )

    ignore_conds = [
        debug_config.load_cmds != ["load"],
        not flash_images,
        not all([os.path.isfile(item["path"]) for item in flash_images]),
    ]

    if any(ignore_conds):
        return

    load_cmds = [
        'monitor program_esp "{{{path}}}" {offset} verify'.format(
            path=to_unix_path(item["path"]), offset=item["offset"]
        )
        for item in flash_images
    ]
    load_cmds.append(
        'monitor program_esp "{%s.bin}" %s verify'
        % (
            to_unix_path(debug_config.build_data["prog_path"][:-4]),
            build_extra_data.get("application_offset", "0x10000"),
        )
    )
    debug_config.load_cmds = load_cmds


