# Homebrew formula for NinjaSRE.
#
# The package-manager path, and it exists for a specific person: the
# operator who will not pipe a script into a shell. Homebrew verifies the
# archive's SHA-256 itself, which is the same integrity guarantee install.sh
# implements by hand — stated once here rather than reimplemented.
#
# No telemetry, no post-install network call, no version check. `brew upgrade`
# is the update path, which is why `ninjasre update` reports rather than
# installs.
class Ninjasre < Formula
  desc "Self-hosted AI SRE platform that investigates incidents and proves it improves"
  homepage "https://github.com/ninjasre/ninjasre"
  license "Apache-2.0"
  version "0.1.0"

  on_macos do
    on_arm do
      url "https://get.ninjasre.dev/v#{version}/ninjasre-v#{version}-darwin-arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://get.ninjasre.dev/v#{version}/ninjasre-v#{version}-darwin-amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  on_linux do
    on_arm do
      url "https://get.ninjasre.dev/v#{version}/ninjasre-v#{version}-linux-arm64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
    on_intel do
      url "https://get.ninjasre.dev/v#{version}/ninjasre-v#{version}-linux-amd64.tar.gz"
      sha256 "0000000000000000000000000000000000000000000000000000000000000000"
    end
  end

  def install
    bin.install "ninjasre"
    generate_completions_from_executable(bin/"ninjasre", "--show-completion", shells: [:bash, :zsh, :fish])
  end

  def caveats
    <<~EOS
      Configure a provider and your integrations:
        ninjasre onboard

      Nothing has been sent anywhere. NinjaSRE has no telemetry, and this
      formula makes no network call after the download above.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/ninjasre --version")
    # The exit-code contract is part of the published interface, so a build
    # that cannot print it is a build that did not package the CLI properly.
    assert_match "0", shell_output("#{bin}/ninjasre --exit-codes")
  end
end
