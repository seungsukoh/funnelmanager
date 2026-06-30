param(
    [Parameter(Mandatory = $true)]
    [string]$MessageJson,

    [ValidateSet("send", "display")]
    [string]$Mode = "send"
)

$ErrorActionPreference = "Stop"

$message = Get-Content -LiteralPath $MessageJson -Raw -Encoding UTF8 | ConvertFrom-Json

$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)

if ($message.account_email) {
    foreach ($account in $outlook.Session.Accounts) {
        if ($account.SmtpAddress -eq $message.account_email) {
            $mail.SendUsingAccount = $account
            break
        }
    }
}

$mail.To = $message.to_email
$mail.Subject = $message.subject
$mail.BodyFormat = 2
$mail.HTMLBody = $message.html_body

if ($Mode -eq "display") {
    $mail.Display($false)
    Write-Output "outlook:displayed"
} else {
    $mail.Send()
    Write-Output "outlook:sent"
}
