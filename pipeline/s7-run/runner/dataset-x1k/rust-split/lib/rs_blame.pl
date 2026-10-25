#!/usr/bin/env perl
# rs_blame.pl: the blame driver of an extra machine (as ec2-user).
# It starts formatBlame.pl exactly as blameRepoFiles.pl of cregit 57551d7 does (line 127):
#   formatBlame.pl --blameExtension=.blame <repo> <name> <outdir>
# with fork + exec, at most --jobs at a time, and the output dirs made before the first fork.
# What differs: the file list. It reads a part file ("index<TAB>size<TAB>name", the index of
# machine A's order) and takes the files from the largest index down, so that machine A (which
# goes up from index 1) and the extras meet in the middle.
# Before each start it skips a file that has a .blame in <outdir> or is in --skip (sent before),
# it stops when --stop-file exists, and it stops when the next index is <= A + --margin, where A
# is the number in --apos-file (machine A's newest started index; read at most every 10 s).
# --margin -1 turns the A rule off (the gate).
# --state DIR gets "progress" (one line, rewritten) and "end" (the reason the loop ended).
# Stdout: one summary line as blameRepoFiles.pl. Stderr: "<count>: <name>" per start, and the
# stderr of formatBlame.pl (PLAIN-BLAME lines). Exit 0 when no file failed.
use strict;
use warnings;
use File::Basename;
use File::Path qw(make_path);
use Getopt::Long;
use Errno qw(EINTR);
use POSIX qw(_exit);

my $blameCommand = '';
my $blameExtension = ".blame";
my $jobs = 1;
my ($partFile, $skipFile, $aposFile, $stopFile, $stateDir) = ('', '', '', '', '');
my $margin = 0;
GetOptions("formatblame=s" => \$blameCommand,
           "jobs=i"        => \$jobs,
           "part=s"        => \$partFile,
           "skip=s"        => \$skipFile,
           "apos-file=s"   => \$aposFile,
           "stop-file=s"   => \$stopFile,
           "margin=i"      => \$margin,
           "state=s"       => \$stateDir)
    or die("Error in command line arguments\n");
die "--jobs must be a positive integer\n" unless $jobs >= 1;
die "--formatblame and --part are needed\n" unless $blameCommand ne '' and $partFile ne '';
die "usage: rs_blame.pl [options] <repository> <outputDirectory>\n" unless scalar(@ARGV) == 2;
my ($repoDir, $outputDir) = @ARGV;

my @part;
open(my $pf, '<', $partFile) or die "unable to read [$partFile]: $!";
while (my $l = <$pf>) {
    chomp $l;
    next if $l eq '';
    my ($i, $s, $name) = split(/\t/, $l, 3);
    die "bad part line [$l]\n" unless defined $name and $i =~ /^[0-9]+$/;
    push @part, [$i + 0, $name];
}
close($pf);
@part = sort { $b->[0] <=> $a->[0] } @part;

my %skip;
if ($skipFile ne '' and -f $skipFile) {
    open(my $sf, '<', $skipFile) or die "unable to read [$skipFile]: $!";
    while (my $l = <$sf>) { chomp $l; $skip{$l} = 1 if $l ne ''; }
    close($sf);
}

my $aPos = 0;
my $aPosRead = 0;
sub a_pos {
    return -1 if $margin < 0 or $aposFile eq '';
    if (time() - $aPosRead >= 10) {
        $aPosRead = time();
        if (open(my $af, '<', $aposFile)) {
            my $l = <$af>;
            close($af);
            $aPos = $1 + 0 if defined $l and $l =~ /^([0-9]+)/ and $1 + 0 > $aPos;
        }
    }
    return $aPos;
}
sub stopped { return $stopFile ne '' && -e $stopFile; }

my $count = 0;
my $alreadyDone = 0;
my $errorCount = 0;
my $lowest = '';
my %running;
my $end = 'part-end';
my $left = scalar(@part);
my $progressAt = 0;

sub progress {
    my ($force) = @_;
    return if $stateDir eq '';
    return if !$force and time() - $progressAt < 30;
    $progressAt = time();
    my $t = "$stateDir/progress.tmp";
    open(my $o, '>', $t) or return;
    printf $o "time %d started %d skipped_done %d errors %d running %d lowest_started %s left_in_queue %d apos %d margin %d jobs %d\n",
        time(), $count, $alreadyDone, $errorCount, scalar(keys %running), ($lowest eq '' ? '-' : $lowest), $left, $aPos, $margin, $jobs;
    close($o);
    rename($t, "$stateDir/progress");
}

# Before the first fork, as blameRepoFiles.pl 120-121.
{
    my %seen;
    foreach my $r (@part) {
        my $dir = dirname("$outputDir/$r->[1]$blameExtension");
        next if $seen{$dir}++;
        next if -d $dir;
        make_path($dir);
        die "unable to create directory [$dir]" unless -d $dir;
    }
}

foreach my $r (@part) {
    my ($i, $name) = @$r;
    reap_command() while scalar(keys %running) >= $jobs;
    $left--;
    if (stopped()) { $end = 'stop'; last; }
    my $a = a_pos();
    if ($a >= 0 and $i <= $a + $margin) { $end = 'met-A'; last; }
    if ($skip{$name} or -f "$outputDir/$name$blameExtension") {
        $alreadyDone++;
        next;
    }
    $count++;
    $lowest = $i;
    print STDERR ("$count: $name\n");
    start_command($name, $blameCommand, "--blameExtension=$blameExtension", $repoDir, $name, $outputDir);
    progress(0);
}

reap_command() while %running;
progress(1);
if ($stateDir ne '') {
    open(my $e, '>', "$stateDir/end") or die "unable to write [$stateDir/end]: $!";
    print $e "$end " . time() . "\n";
    close($e);
}
print "Newly processed [$count] Already done [$alreadyDone] files Error [$errorCount] End [$end]\n";
exit($errorCount == 0 ? 0 : 1);

sub start_command {
    my ($name, @command) = @_;
    my $pid = fork();
    if (!defined $pid) {
        print "Unable to start command [$name]: $!\n";
        $errorCount++;
        return;
    }
    if ($pid == 0) {
        exec { $command[0] } @command;
        print STDERR "Unable to execute command [$command[0]]: $!\n";
        _exit(127);
    }
    $running{$pid} = $name;
}

sub reap_command {
    my $pid;
    do {
        $pid = wait();
    } while ($pid < 0 && $! == EINTR);
    die "unable to wait for formatter process: $!" if $pid < 0;
    my $status = $?;
    my $name = delete $running{$pid};
    if ($status != 0) {
        print "Error code [$status][$name]\n";
        $errorCount++;
    }
}
