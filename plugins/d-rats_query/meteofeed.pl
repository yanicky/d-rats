#!/usr/bin/perl
# import packages
use XML::RSS;
use LWP::Simple;
use HTML::Parse;
use HTML::FormatText;
# initialize object
$rss = new XML::RSS();
# get RSS data
$raw = get('http://www.meteogiornale.it/api/rss/it/scandicci.xml');
die "Couldn't get it!" unless defined $raw;
# parse RSS feed
$rss->parse($raw);
# print titles and URLs of news items
foreach my $item (@{$rss->{'items'}})
{
	print "\n".$item->{'title'}."\n\n";
	$description = HTML::FormatText->new->format(parse_html($item->{'description'}));
	$description =~ s/[\t\f\r]+//gs;
	$description =~ s/\v/\n/gs;
	$description =~ s/ +/ /gs;
	$description =~ s/\n /\n/gs;
	$description =~ s/\n\n/\n/gs;
	$description =~ s/[^a-zA-Z0-9\/: \n]//gs;
	print $description."\n";
}
;
