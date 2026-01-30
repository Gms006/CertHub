using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace Certhub.Agent.Services;

public static class CertificateEntityKey
{
    private static readonly Regex EntityKeyInCnPattern = new(
        @"CN\s*=\s*[^,]*:\s*([0-9]{11}|[0-9]{14})",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    public static string? ExtractEntityKey(string? subject)
    {
        if (string.IsNullOrWhiteSpace(subject))
        {
            return null;
        }

        var match = EntityKeyInCnPattern.Match(subject);
        if (!match.Success)
        {
            return null;
        }

        return match.Groups[1].Value;
    }

    public static string MaskSubjectForLog(string? subject, int maxLength = 120)
    {
        if (string.IsNullOrWhiteSpace(subject))
        {
            return string.Empty;
        }

        var masked = Regex.Replace(subject, "[0-9]", "*");
        if (masked.Length <= maxLength)
        {
            return masked;
        }

        if (maxLength <= 1)
        {
            return masked[..maxLength];
        }

        return masked[..(maxLength - 1)] + "…";
    }

    public static string HashEntityKey(string entityKey)
    {
        using var sha256 = SHA256.Create();
        var bytes = Encoding.UTF8.GetBytes(entityKey);
        var hash = sha256.ComputeHash(bytes);
        var builder = new StringBuilder(hash.Length * 2);
        foreach (var value in hash)
        {
            builder.Append(value.ToString("x2"));
        }

        return builder.ToString();
    }
}
