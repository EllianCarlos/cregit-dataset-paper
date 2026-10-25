#!/usr/bin/env perl
# rs_order.pl REPO OUTDIR MASK DONE_OUT (machine A, as ec2-user; read-only).
# The file list of blameRepoFiles.pl of cregit 57551d7 (lines 65-118), with no blame.
# The code below is a copy of those lines: plain git ls-files (no -z), the mask as a Perl
# regex, the -f checks, the skip check of an existing .blame, and the sort (size desc, then
# ls-files order). So the order is the order of the running step 7.
# Stdout: "index<TAB>size<TAB>name" for each file left (index 1 = the first file of the run).
# DONE_OUT: "size<TAB>name" for each file that has a .blame. Stderr: the counts.
use strict;
use warnings;

die "usage: rs_order.pl REPO OUTDIR MASK DONE_OUT\n" unless scalar(@ARGV) == 4;
my ($repoDir, $outputDir, $fileRegExpr, $doneOut) = @ARGV;
my $blameExtension = ".blame";

open(my $files, '-|', 'git', '-C', $repoDir, 'ls-files')
    or die "unable to traverse git repo [$repoDir] $!";
my @trackedFiles = <$files>;
close($files) or die "unable to traverse git repo [$repoDir]";

my $matched = 0;
my $alreadyDone = 0;
my @filesToBlame;
my @done;

foreach (@trackedFiles) {
    chomp;
    if ($fileRegExpr ne "") {
        next unless /$fileRegExpr/;
    }
    my $name = $_;
    my $originalFile = $repoDir . "/" . $name;
    my $outputFile = $outputDir . "/" . $name . $blameExtension;
    next unless -f $originalFile;
    next unless (-f $originalFile > 0);
    $matched++;
    if (-f $outputFile) {
        $alreadyDone++;
        push @done, $name;
        next;
    }
    push @filesToBlame, $name;
}

# The sort of blameRepoFiles.pl 104-118: largest first, ties keep the ls-files order.
my %sizeOf;
foreach my $name (@filesToBlame) {
    $sizeOf{$name} = -s "$repoDir/$name" || 0;
}
my $i = 0;
my %order = map { $_ => $i++ } @filesToBlame;
@filesToBlame = sort {
    $sizeOf{$b} <=> $sizeOf{$a}
        or
    $order{$a} <=> $order{$b}
} @filesToBlame;

my $n = 0;
foreach my $name (@filesToBlame) {
    $n++;
    print "$n\t$sizeOf{$name}\t$name\n";
}
open(my $d, '>', $doneOut) or die "unable to write [$doneOut]: $!";
foreach my $name (@done) {
    my $s = -s "$repoDir/$name" || 0;
    print $d "$s\t$name\n";
}
close($d) or die "unable to close [$doneOut]: $!";
print STDERR "tracked " . scalar(@trackedFiles) . " mask $matched done $alreadyDone left " . scalar(@filesToBlame) . "\n";
