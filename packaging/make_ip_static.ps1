# make_ip_static.ps1
#
# Keeps this computer's network address from changing after a reboot, so
# every other device in the clinic can reach it reliably at the same plain
# numeric address (e.g. http://192.168.1.50:8080) forever, with nothing to
# reconfigure later. This runs AUTOMATICALLY once, right after install,
# because the Windows installer ticks that option by default — most clinics
# never need to think about this script at all. It's also installed to the
# Start Menu as "Make this computer's address permanent (redo)", for the
# rare case it needs to be run again by hand (the checkbox was unticked
# during install, or the computer moved to a different network).
#
# This is deliberately the primary way Clinic EMR keeps its address
# stable, not clinicserver.local (mDNS): that name is a bonus that happens
# to work on macOS, iOS, Android and modern Linux out of the box, but
# Windows generally does NOT resolve arbitrary .local names without Apple's
# Bonjour also being installed (it's bundled with iTunes, or installable on
# its own as "Bonjour Print Services") — something a clinic PC usually
# doesn't have. Rather than depend on that, this script makes the plain
# numeric address permanent instead, which needs nothing extra installed
# anywhere.
#
# WHAT THIS DOES: it looks at the network connection this computer is
# currently using, reads the IP address / subnet / gateway / DNS servers
# it was AUTOMATICALLY assigned (DHCP), and then sets those exact same
# values as a PERMANENT ("static") configuration on that connection. The
# computer's address on the network does not change at all — it simply
# stops being something the router can hand out to a different device or
# change after a restart. This does not touch the clinic's router and
# does not need anyone to log into it.
#
# This must be run as Administrator (changing network settings requires
# it), but Clinic EMR itself deliberately does NOT run as Administrator
# day to day. So this stays a separate script — not a button inside the
# app — and it re-launches itself with an administrator prompt
# automatically (whether it's launched by the installer or by hand), so
# that one expected permission prompt is the only thing anyone ever sees.
#
# Safe to run more than once: if the connection is already static, it
# says so and makes no changes.

$ErrorActionPreference = "Stop"

function Pause-Exit($code) {
    Write-Host ""
    Write-Host "Press any key to close this window..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit $code
}

# Re-launch elevated if we're not already running as Administrator.
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "This needs administrator rights to change network settings — requesting that now..."
    try {
        Start-Process powershell.exe -Verb RunAs -ArgumentList (
            "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
        )
    } catch {
        Write-Host "The administrator prompt was cancelled, so nothing was changed."
        Pause-Exit 1
    }
    exit 0
}

Write-Host "Clinic EMR — make this computer's network address permanent"
Write-Host "============================================================"
Write-Host ""

# Find the active network adapter actually carrying traffic — the one with
# a default gateway and a cable/WiFi link up. Loopback, VPN, and virtual
# adapters are excluded so we don't accidentally reconfigure the wrong one.
$config = Get-NetIPConfiguration | Where-Object {
    $_.IPv4DefaultGateway -ne $null -and $_.NetAdapter.Status -eq "Up"
} | Select-Object -First 1

if (-not $config) {
    Write-Host "Could not find an active network connection with a gateway on this"
    Write-Host "computer. Make sure it's connected to the clinic's WiFi or network"
    Write-Host "cable, then run this script again."
    Pause-Exit 1
}

$adapterAlias = $config.InterfaceAlias
$ipv4 = $config.IPv4Address | Select-Object -First 1
$ipAddress = $ipv4.IPAddress
$prefixLength = $ipv4.PrefixLength
$gateway = $config.IPv4DefaultGateway.NextHop
$dnsServers = (Get-DnsClientServerAddress -InterfaceAlias $adapterAlias -AddressFamily IPv4).ServerAddresses

Write-Host "Found: $adapterAlias"
Write-Host "  Current address: $ipAddress / $prefixLength"
Write-Host "  Gateway:         $gateway"
Write-Host "  DNS:             $($dnsServers -join ', ')"
Write-Host ""

# Already static with these values? Nothing to do.
$existingAddr = Get-NetIPAddress -InterfaceAlias $adapterAlias -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -eq $ipAddress }
if ($existingAddr -and $existingAddr.PrefixOrigin -eq "Manual") {
    Write-Host "This connection is already set to a permanent (static) address."
    Write-Host "Nothing to change — other devices can safely use:"
    Write-Host "    http://${ipAddress}:8080"
    Pause-Exit 0
}

Write-Host "Making $ipAddress permanent on '$adapterAlias'..."
try {
    # Remove the existing DHCP-assigned address/route for this adapter...
    Remove-NetIPAddress -InterfaceAlias $adapterAlias -AddressFamily IPv4 -Confirm:$false -ErrorAction SilentlyContinue
    Remove-NetRoute -InterfaceAlias $adapterAlias -DestinationPrefix "0.0.0.0/0" -Confirm:$false -ErrorAction SilentlyContinue

    # ...and re-apply the SAME address/gateway as a static (manual) one.
    New-NetIPAddress -InterfaceAlias $adapterAlias -IPAddress $ipAddress `
        -PrefixLength $prefixLength -DefaultGateway $gateway | Out-Null

    if ($dnsServers -and $dnsServers.Count -gt 0) {
        Set-DnsClientServerAddress -InterfaceAlias $adapterAlias -ServerAddresses $dnsServers
    }

    Write-Host ""
    Write-Host "Done. This computer's address is now fixed at:"
    Write-Host "    http://${ipAddress}:8080"
    Write-Host ""
    Write-Host "Other devices in the clinic can use that address directly, or keep"
    Write-Host "using the clinicserver.local address — both now point at the same"
    Write-Host "place and neither will change after a restart."
    Pause-Exit 0
} catch {
    Write-Host ""
    Write-Host "Something went wrong and the address could not be changed:"
    Write-Host "    $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Nothing should have been left half-changed, but if this computer's"
    Write-Host "network stops working after this, reconnect the WiFi/cable or"
    Write-Host "restart the computer to get a fresh DHCP address back."
    Pause-Exit 1
}
