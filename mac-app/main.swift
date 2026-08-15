import SwiftUI
import AppKit

// Pi 설정 — album-display 프로젝트의 SSH 대상과 동일
let piHost = "banshk@172.30.1.49"
let piDir = "/home/banshk/album-display"
let sshBin = "/usr/bin/ssh"
let scpBin = "/usr/bin/scp"
let sshOpts = ["-o", "ConnectTimeout=5"]

// ssh/scp를 절대경로로 직접 호출 — PATH 의존은 이 프로젝트에서 반복적으로 문제였다(launchd/cron 사고 참고).
@discardableResult
func run(_ launchPath: String, _ args: [String]) -> (status: Int32, output: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: launchPath)
    process.arguments = args

    let pipe = Pipe()
    process.standardOutput = pipe
    process.standardError = pipe

    do {
        try process.run()
    } catch {
        return (-1, "실행 실패: \(error.localizedDescription)")
    }

    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    let output = String(data: data, encoding: .utf8) ?? ""
    return (process.terminationStatus, output)
}

func sshCommand(_ remoteCommand: String) -> (status: Int32, output: String) {
    run(sshBin, sshOpts + [piHost, remoteCommand])
}

func showAlert(title: String, message: String) {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    alert.alertStyle = .informational
    alert.runModal()
}

func checkTemperature() {
    let (status, output) = sshCommand("vcgencmd measure_temp; vcgencmd get_throttled")
    if status != 0 {
        showAlert(title: "온도 확인 실패", message: "Pi에 연결할 수 없습니다.\n\(output)")
        return
    }
    showAlert(title: "Pi 상태", message: output.trimmingCharacters(in: .whitespacesAndNewlines))
}

func rebootPi() {
    let confirm = NSAlert()
    confirm.messageText = "정말 재부팅할까요?"
    confirm.informativeText = "디스플레이가 잠깐(약 1분) 꺼졌다 다시 켜집니다. 전원을 완전히 끄는 게 아니라 재부팅이라 원격으로 다시 켤 수 있습니다."
    confirm.alertStyle = .warning
    confirm.addButton(withTitle: "재부팅")
    confirm.addButton(withTitle: "취소")
    guard confirm.runModal() == .alertFirstButtonReturn else { return }

    let (status, output) = sshCommand("sudo reboot")
    // reboot는 연결이 끊기면서 비정상 종료 코드를 내는 게 정상이라 status는 판단 기준으로 안 씀
    _ = status
    showAlert(title: "재부팅 명령 전송됨", message: output.isEmpty ? "약 1분 후 다시 접속됩니다." : output)
}

func uploadImage() {
    let panel = NSOpenPanel()
    panel.allowedContentTypes = [.image]
    panel.allowsMultipleSelection = false
    panel.canChooseDirectories = false
    guard panel.runModal() == .OK, let url = panel.url else { return }

    let remoteTmpPath = "\(piDir)/incoming_upload.jpg"
    let (scpStatus, scpOutput) = run(scpBin, sshOpts + [url.path, "\(piHost):\(remoteTmpPath)"])
    guard scpStatus == 0 else {
        showAlert(title: "업로드 실패", message: "사진을 Pi로 전송하지 못했습니다.\n\(scpOutput)")
        return
    }

    let (showStatus, showOutput) = sshCommand("cd \(piDir) && python3 show_image.py \(remoteTmpPath)")
    if showStatus != 0 {
        showAlert(title: "표시 실패", message: showOutput)
        return
    }
    showAlert(title: "전송 완료", message: "화면에 잠깐(약 10초) 표시됩니다.")
}

// LED 매트릭스만 끈다(Pi 자체는 계속 켜져 있음) — 리프레시 신호가 끊기면 패널이 바로 꺼지는 구조라
// 발열/전력의 대부분을 차지하는 매트릭스를 물리적으로 손 안 대고 줄일 수 있다.
func setSleepMode(_ enabled: Bool) {
    let action = enabled ? "stop" : "start"
    let (status, output) = sshCommand("sudo systemctl \(action) album-display")
    if status != 0 {
        showAlert(title: "실패", message: output)
        return
    }
    showAlert(title: enabled ? "절전모드 켜짐" : "절전모드 꺼짐",
              message: enabled ? "LED 매트릭스가 꺼졌습니다. Pi는 계속 켜져 있어 다시 켤 수 있습니다."
                                : "디스플레이가 다시 켜졌습니다.")
}

struct MenuContent: View {
    var body: some View {
        Button("🌡 온도 확인") { checkTemperature() }
        Button("🖼 이미지 업로드…") { uploadImage() }
        Divider()
        Button("🌙 절전모드 켜기") { setSleepMode(true) }
        Button("☀️ 절전모드 끄기") { setSleepMode(false) }
        Divider()
        Button("🔄 재부팅") { rebootPi() }
        Divider()
        Button("종료") { NSApplication.shared.terminate(nil) }
    }
}

@main
struct AlbumDisplayControlApp: App {
    var body: some Scene {
        MenuBarExtra("앨범 디스플레이", systemImage: "square.grid.3x3.fill") {
            MenuContent()
        }
        .menuBarExtraStyle(.menu)
    }
}
